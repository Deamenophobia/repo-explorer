"""Read immutable Git blobs or hash-verified files without executing repository code."""

import hashlib
import json
import subprocess
from pathlib import Path

from repo_explorer.evaluation.models import EvaluationSuite

MAX_FILE_BYTES = 200_000


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_text(data: bytes) -> str:
    # Keep fixture identities stable across Git's LF/CRLF checkout conventions.
    text = data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    if "\x00" in text:
        raise ValueError("Binary content is outside this text evaluation's scope.")
    return text


def git(repository: Path, *args: str) -> bytes:
    command = ["git", "--no-replace-objects", "--literal-pathspecs", "-C", str(repository), *args]
    result = subprocess.run(command, capture_output=True, check=False, timeout=30)
    if result.returncode:
        raise ValueError(
            "Cannot read the requested Git object; check repository, revision and path."
        )
    return result.stdout


def read_snapshot(suite: EvaluationSuite, repository: Path) -> dict[str, str]:
    root = repository.resolve(strict=True)
    revision = suite.snapshot.revision
    if revision and git(root, "cat-file", "-t", revision).strip() != b"commit":
        raise ValueError("The pinned revision must identify a commit.")
    sources = {}
    for file in suite.snapshot.files:
        if revision:
            entries = git(root, "ls-tree", "-z", revision, "--", file.path).split(b"\0")
            entries = [entry for entry in entries if entry]
            if len(entries) != 1:
                raise ValueError(f"Missing or ambiguous snapshot path: {file.path}")
            metadata, name = entries[0].split(b"\t", 1)
            mode, kind, oid = metadata.decode().split()
            if name.decode() != file.path or mode not in {"100644", "100755"} or kind != "blob":
                raise ValueError(f"Only regular source files are supported: {file.path}")
            if int(git(root, "cat-file", "-s", oid)) > MAX_FILE_BYTES:
                raise ValueError(f"Source exceeds the evaluation file limit: {file.path}")
            content = git(root, "cat-file", "blob", oid)
        else:
            path = root / file.path
            if not path.resolve(strict=True).is_relative_to(root):
                raise ValueError("Source escapes the configured repository.")
            if any(part.is_symlink() for part in (path, *path.parents) if part != root):
                raise ValueError("Symlinks are not supported by the file snapshot reader.")
            if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
                raise ValueError(f"Unsupported or oversized source: {file.path}")
            content = path.read_bytes()
        text = canonical_text(content)
        if digest(text.encode()) != file.sha256:
            raise ValueError(f"Source hash mismatch: {file.path}")
        sources[file.path] = text
    for case in suite.cases:
        for item in case.evidence:
            lines = sources[item.path].split("\n")
            if item.end_line > len(lines) or item.quote not in "\n".join(
                lines[item.start_line - 1 : item.end_line]
            ):
                raise ValueError(f"Evidence anchor does not match source: {case.id}/{item.id}")
    return sources


def snapshot_id(sources: dict[str, str]) -> str:
    manifest = {path: digest(text.encode()) for path, text in sorted(sources.items())}
    return digest(json.dumps(manifest, sort_keys=True).encode())

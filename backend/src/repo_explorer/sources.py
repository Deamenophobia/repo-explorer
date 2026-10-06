"""Corpus adapter: file discovery is independent of retrieval and generation."""

import hashlib
from dataclasses import dataclass, field

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from repo_explorer.config import Settings


@dataclass
class CorpusSnapshot:
    documents: list[Document]
    files: list[dict]
    policy: str
    texts: dict[str, str] = field(default_factory=dict)


def local_source(settings: Settings) -> CorpusSnapshot:
    root = settings.corpus_dir.resolve(strict=True)
    documents, files, texts = [], [], {}
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap, add_start_index=True
    )
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in settings.excluded_dirs or part.startswith(".") for part in relative.parts):
            continue
        if not path.is_file() or path.suffix not in settings.extensions or path.is_symlink():
            continue
        if not path.resolve().is_relative_to(root) or path.stat().st_size > settings.max_file_bytes:
            continue
        source = path.read_text(encoding="utf-8")
        revision = hashlib.sha256(source.encode()).hexdigest()[:12]
        files.append({"path": relative.as_posix(), "revision": revision})
        texts[relative.as_posix()] = source
        for chunk in splitter.create_documents([source]):
            line = source[: chunk.metadata["start_index"]].count("\n") + 1
            chunk.metadata = {
                "path": relative.as_posix(),
                "revision": revision,
                "start_line": line,
                "end_line": line + chunk.page_content.count("\n"),
            }
            documents.append(chunk)
            if len(documents) > settings.max_chunks:
                raise ValueError(
                    "Index chunk limit exceeded; narrow the corpus or change its limit."
                )
    policy_path = root / settings.policy_file
    if policy_path.is_symlink() or not policy_path.resolve().is_relative_to(root):
        raise ValueError("Policy must be inside the configured corpus.")
    if policy_path.exists() and policy_path.stat().st_size > settings.max_file_bytes:
        raise ValueError("Policy exceeds the configured file size limit.")
    policy = policy_path.read_text(encoding="utf-8") if policy_path.is_file() else ""
    return CorpusSnapshot(documents, files, policy, texts)

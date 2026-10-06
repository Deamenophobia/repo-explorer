import json
import subprocess

import pytest
from pydantic import ValidationError
from repo_explorer.evaluation.models import EvaluationSuite, RetrievalConfig
from repo_explorer.evaluation.runner import run_evaluation, score_evidence
from repo_explorer.evaluation.snapshot import canonical_text, digest, read_snapshot


@pytest.fixture
def source_suite(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    text = "def approve_plan():\n    return 'approval accepted'\n"
    (root / "review.py").write_text(text, encoding="utf-8", newline="\n")
    suite = EvaluationSuite.model_validate(
        {
            "name": "Approval fixture",
            "scope": "A small test fixture.",
            "snapshot": {"files": [{"path": "review.py", "sha256": digest(text.encode())}]},
            "cases": [
                {
                    "id": "approve",
                    "question": "What does approve_plan return?",
                    "reference_notes": "REFERENCE_NOT_FOR_RETRIEVAL",
                    "evidence": [
                        {
                            "id": "return",
                            "path": "review.py",
                            "start_line": 1,
                            "end_line": 2,
                            "quote": "return 'approval accepted'",
                        }
                    ],
                },
                {
                    "id": "absent",
                    "question": "zyzzyva quokka nebula",
                    "unanswerable": True,
                    "reference_notes": "No matching evidence exists in this fixture.",
                },
            ],
        }
    )
    return root, suite


def test_runner_isolated_from_live_settings_and_reference_notes(
    source_suite, tmp_path, monkeypatch
):
    root, suite = source_suite
    monkeypatch.setenv("REPO_EXPLORER_MODE", "live")
    monkeypatch.setenv("REPO_EXPLORER_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("REPO_EXPLORER_CORPUS_DIR", "nonexistent")
    monkeypatch.setenv("REPO_EXPLORER_LEXICAL_TOKENIZATION", "code_identifiers")

    def forbidden():
        raise AssertionError("Evaluation must not load server plugins")

    monkeypatch.setattr("repo_explorer.plugins.default_registry", forbidden)
    destination = tmp_path / "result"
    report = run_evaluation(suite, root, destination)
    assert report["model_calls"] == 0
    assert len(report["implementation_sha256"]) == 64
    assert report["method_configs"]["tfidf"]["lexical_tokenization"] == "standard"
    assert report["method_configs"]["tfidf_identifiers"]["lexical_tokenization"] == (
        "code_identifiers"
    )
    assert report["cases"][0]["methods"]["tfidf"]["evidence_coverage"] == 1
    assert report["cases"][1]["methods"]["tfidf"]["returned_context_on_unanswerable"] is False
    assert (
        report["cases"][1]["methods"]["tfidf_identifiers"]["returned_context_on_unanswerable"]
        is False
    )
    for case in report["cases"]:
        for method in case["methods"].values():
            assert all(
                "REFERENCE_NOT_FOR_RETRIEVAL" not in hit["excerpt"] for hit in method["hits"]
            )
    assert (destination / "report.md").exists()
    assert (destination / "corpus/review.py").read_text() == (root / "review.py").read_text()
    with pytest.raises(FileExistsError):
        run_evaluation(suite, root, destination)


def test_hash_or_anchor_drift_fails_before_output(source_suite, tmp_path):
    root, suite = source_suite
    modified = suite.model_copy(deep=True)
    modified.cases[0].evidence[0].quote = "unsupported invented claim"
    with pytest.raises(ValueError, match="anchor"):
        run_evaluation(modified, root, tmp_path / "bad-anchor")
    (root / "review.py").write_text("modified source")
    with pytest.raises(ValueError, match="hash mismatch"):
        run_evaluation(suite, root, tmp_path / "bad-hash")
    assert not (tmp_path / "bad-anchor").exists()
    assert not (tmp_path / "bad-hash").exists()


def test_line_endings_do_not_change_snapshot_identity(source_suite):
    root, suite = source_suite
    text = (root / "review.py").read_text()
    (root / "review.py").write_bytes(text.replace("\n", "\r\n").encode())
    assert read_snapshot(suite, root)["review.py"] == text
    assert canonical_text(text.encode()) == text


@pytest.mark.parametrize(
    "path",
    ["../outside.py", "/absolute.py", "C:/outside.py", "folder\\source.py", ".env", "./review.py"],
)
def test_snapshot_rejects_unsafe_paths(source_suite, path):
    _, suite = source_suite
    data = suite.model_dump()
    data["snapshot"]["files"][0]["path"] = path
    with pytest.raises(ValidationError):
        EvaluationSuite.model_validate(data)


def test_git_snapshot_uses_pinned_objects_even_with_worktree_changes(source_suite):
    root, suite = source_suite

    def command(*args):
        return subprocess.check_output(["git", "-C", str(root), *args]).decode().strip()

    command("init", "--quiet")
    command("-c", "core.autocrlf=false", "add", "review.py")
    command(
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--quiet",
        "-m",
        "fixture",
    )
    commit = command("rev-parse", "HEAD")
    data = suite.model_dump()
    data["snapshot"].update(kind="git", revision=commit)
    pinned = EvaluationSuite.model_validate(data)
    original = read_snapshot(pinned, root)
    (root / "review.py").write_text("uncommitted content must not enter the snapshot")
    assert read_snapshot(pinned, root) == original
    assert "uncommitted content" in (root / "review.py").read_text()


def test_partial_line_does_not_receive_full_evidence_credit(source_suite):
    _, suite = source_suite
    case = suite.cases[0].model_copy(deep=True)
    case.evidence[0].start_line = case.evidence[0].end_line = 1
    sources = {"review.py": "allow(); deny();\n"}
    first = {"path": "review.py", "start_line": 1, "end_line": 1, "excerpt": "allow();"}
    second = {**first, "excerpt": "deny();"}
    assert score_evidence(case, [first], sources)["evidence_coverage"] == 0
    assert score_evidence(case, [first], sources)["evidence"][0]["missing_lines"] == [1]
    assert score_evidence(case, [first, second], sources)["evidence_coverage"] == 1


def test_replay_preserves_results_and_never_uses_annotated_answers(source_suite, tmp_path):
    root, suite = source_suite
    first = run_evaluation(suite, root, tmp_path / "first", RetrievalConfig(retrieval_limit=1))
    replay = run_evaluation(
        suite, tmp_path / "first/corpus", tmp_path / "second", RetrievalConfig(retrieval_limit=1)
    )
    assert first["snapshot_id"] == replay["snapshot_id"]
    for left, right in zip(first["cases"], replay["cases"], strict=True):
        for method in left["methods"]:
            assert left["methods"][method]["hits"] == right["methods"][method]["hits"]
            assert left["methods"][method]["evidence"] == right["methods"][method]["evidence"]
    stored = json.loads((tmp_path / "first/config.json").read_text())
    assert stored["retrieval_limit"] == 1


def test_annotations_and_coverage_share_ingestion_line_numbers(source_suite):
    root, suite = source_suite
    source = "label = 'unicode\u2028separator'\nvalue = 'approval accepted'\n"
    (root / "review.py").write_text(source, encoding="utf-8")
    suite.snapshot.files[0].sha256 = digest(source.encode())
    evidence = suite.cases[0].evidence[0]
    evidence.start_line = evidence.end_line = 2
    evidence.quote = "value = 'approval accepted'"
    sources = read_snapshot(suite, root)
    hit = {"path": "review.py", "start_line": 2, "end_line": 2, "excerpt": evidence.quote}
    assert score_evidence(suite.cases[0], [hit], sources)["evidence_coverage"] == 1

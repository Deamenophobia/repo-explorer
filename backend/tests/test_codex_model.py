import json
import os
import subprocess
import traceback
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langchain_core.callbacks import UsageMetadataCallbackHandler
from pydantic import ValidationError
from repo_explorer.api import create_app
from repo_explorer.codex_model import CodexChatModel, CodexInvocationError, parse_codex_events
from repo_explorer.config import Settings, WorkspaceConfig
from repo_explorer.generation import ChatAnswerGenerator

ROOT = Path(__file__).resolve().parents[2]


def events(answer="Source explanation [S1].", **overrides):
    response = {
        "answer": answer,
        "citation_ids": ["S1"],
        "answerability": "complete",
        "limitations": [],
    }
    items = [
        {"type": "thread.started", "thread_id": "fixture"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {
                "type": "agent_message",
                "text": json.dumps(response),
            },
        },
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 15,
                "cached_input_tokens": 20,
            },
        },
    ]
    return SimpleNamespace(
        returncode=0, stdout="\n".join(json.dumps(item) for item in items), stderr="", **overrides
    )


def test_prompt_is_stdin_and_invocation_keeps_only_schema_and_instructions(tmp_path, monkeypatch):
    seen = []

    def invoke(command, **kwargs):
        seen.append(kwargs["cwd"])
        root = Path(kwargs["cwd"])
        assert set(path.name for path in root.iterdir()) == {"schema.json", "instructions.txt"}
        assert "POLICY_FIXTURE" in (root / "instructions.txt").read_text(encoding="utf-8")
        assert json.loads((root / "schema.json").read_text())["additionalProperties"] is False
        assert "UNTRUSTED_SOURCE_TEXT" in kwargs["input"]
        assert "UNTRUSTED_SOURCE_TEXT" not in " ".join(command)
        assert "--ignore-user-config" in command and "--ephemeral" in command
        assert command[command.index("--sandbox") + 1] == "read-only"
        assert "features.shell_tool=false" in command
        assert "features.plugins=false" in command
        assert "features.multi_agent=false" in command
        assert 'web_search="disabled"' in command
        assert "project_doc_max_bytes=0" in command
        assert kwargs["timeout"] == 17
        assert not kwargs.get("shell", False)
        return events()

    monkeypatch.setattr("repo_explorer.codex_model.subprocess.run", invoke)
    settings = Settings(mode="live", model="fixture", chat_provider="codex", request_timeout=17)
    model = CodexChatModel(executable="fixture.exe", model_name="fixture", timeout_seconds=17)
    generator = ChatAnswerGenerator(settings, model)
    usage = UsageMetadataCallbackHandler()
    result = generator.chain.invoke(
        {
            "question": "What happens?",
            "intent": "question",
            "policy": "POLICY_FIXTURE",
            "sources": "UNTRUSTED_SOURCE_TEXT",
        },
        config={"callbacks": [usage]},
    )
    assert result.citation_ids == ["S1"]
    assert usage.usage_metadata["fixture"]["total_tokens"] == 115
    assert usage.usage_metadata["fixture"]["input_token_details"]["cache_read"] == 20
    assert not seen[0].exists()


@pytest.mark.parametrize(
    "kind", ["command_execution", "mcp_tool_call", "web_search", "file_change"]
)
def test_tool_activity_cannot_be_reported_as_a_grounded_answer(kind):
    output = json.dumps({"type": "item.started", "item": {"type": kind}}) + "\n" + events().stdout
    with pytest.raises(CodexInvocationError, match="tool action"):
        parse_codex_events(output)


@pytest.mark.parametrize(
    "output,code",
    [
        ("not-json SECRET", "invalid_event_stream"),
        ("[]", "invalid_event_stream"),
        ('{"type":[]}', "invalid_event_stream"),
        ('{"type":"item.completed","item":null}', "invalid_event_stream"),
        ('{"type":"item.completed","item":{"type":[]}}', "invalid_event_stream"),
        ('{"type":"turn.failed","error":{"message":"SECRET"}}', "turn_failed"),
        ('{"type":"error","message":"SECRET"}', "stream_error"),
        ('{"type":"turn.completed"}', "missing_answer"),
        ('{"type":"turn.completed","usage":[]}', "invalid_usage"),
        (
            '{"type":"item.completed","item":{"type":"agent_message","text":"unfinished"}}',
            "missing_completion",
        ),
    ],
)
def test_malformed_failed_or_incomplete_turn_fails_without_exposing_cli_output(output, code):
    with pytest.raises(CodexInvocationError) as raised:
        parse_codex_events(output, exit_code=0)
    assert raised.value.code == code
    assert raised.value.exit_code == 0
    assert "SECRET" not in str(raised.value)


@pytest.mark.parametrize("exit_code", [0, 1])
def test_explicit_turn_failure_survives_cli_exit_status(exit_code, monkeypatch):
    from repo_explorer.evaluation.live import safe_error

    monkeypatch.setattr(
        "repo_explorer.codex_model.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=exit_code,
            stdout='{"type":"turn.failed","error":{"message":"SECRET_PROVIDER_BODY"}}',
            stderr="SECRET_STDERR",
        ),
    )
    generator = ChatAnswerGenerator(
        Settings(mode="live", model="fixture"),
        CodexChatModel(executable="fixture.exe", model_name="fixture"),
    )
    with pytest.raises(CodexInvocationError) as raised:
        generator.generate("What happens?", "question", [], "")
    saved = safe_error("generation", raised.value)
    assert saved["code"] == "turn_failed"
    assert saved["exit_code"] == exit_code
    assert "SECRET" not in json.dumps(saved)
    assert "SECRET" not in "".join(traceback.format_exception(raised.value))


def test_unsuccessful_exit_cannot_accept_a_completed_answer():
    with pytest.raises(CodexInvocationError) as raised:
        parse_codex_events(events().stdout, exit_code=1)
    assert raised.value.code == "cli_failed"
    assert raised.value.exit_code == 1


@pytest.mark.parametrize(
    "draft", ["PRIVATE_MODEL_OUTPUT", '{"answer":"PRIVATE_MODEL_OUTPUT","citation_ids":false}']
)
def test_invalid_structured_output_is_classified_without_leaking_model_text(draft, monkeypatch):
    result = events()
    records = [json.loads(line) for line in result.stdout.splitlines()]
    records[2]["item"]["text"] = draft
    result.stdout = "\n".join(json.dumps(record) for record in records)
    monkeypatch.setattr("repo_explorer.codex_model.subprocess.run", lambda *args, **kwargs: result)
    generator = ChatAnswerGenerator(
        Settings(mode="live", model="fixture"),
        CodexChatModel(executable="fixture.exe", model_name="fixture"),
    )
    with pytest.raises(CodexInvocationError) as raised:
        generator.generate("What happens?", "question", [], "")
    assert raised.value.code == "invalid_structured_output"
    assert "PRIVATE_MODEL_OUTPUT" not in "".join(traceback.format_exception(raised.value))


@pytest.mark.parametrize("failure", ["timeout", "exit"])
def test_process_errors_are_safe_and_do_not_retry(failure, monkeypatch):
    count = 0

    def invoke(command, **kwargs):
        nonlocal count
        count += 1
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 1, output="PRIVATE_SOURCE", stderr="SECRET")
        return SimpleNamespace(returncode=1, stdout="PRIVATE_SOURCE", stderr="SECRET")

    monkeypatch.setattr("repo_explorer.codex_model.subprocess.run", invoke)
    generator = ChatAnswerGenerator(
        Settings(mode="live", model="fixture"),
        CodexChatModel(executable="fixture.exe", model_name="fixture"),
    )
    with pytest.raises(CodexInvocationError) as raised:
        generator.generate("What happens?", "question", [], "")
    assert count == 1
    assert "SECRET" not in str(raised.value) and "PRIVATE_SOURCE" not in str(raised.value)


def test_codex_provider_uses_existing_api_graph_and_review_gate(tmp_path, monkeypatch):
    monkeypatch.setattr("repo_explorer.codex_model.codex_version", lambda _: "codex-cli fixture")
    monkeypatch.setattr(
        "repo_explorer.codex_model.resolve_codex_executable", lambda _: "fixture.exe"
    )
    calls = []

    def invoke(command, **kwargs):
        calls.append(command)
        assert kwargs["env"]["HTTPS_PROXY"] == "http://operator:private-proxy@localhost:8080"
        return events()

    monkeypatch.setattr("repo_explorer.codex_model.subprocess.run", invoke)
    settings = Settings(
        corpus_dir=ROOT / "examples/repository",
        data_dir=tmp_path / "data",
        config_file=tmp_path / "settings.json",
        codex_executable="fixture.exe",
        codex_proxy_url="http://operator:private-proxy@localhost:8080",
    )
    with TestClient(create_app(settings)) as client:
        document = client.get("/api/settings").json()
        assert "codex" in document["adapters"]["chat"]
        assert "codex_executable" not in document["values"]
        assert "codex_proxy_url" not in document["values"]
        assert "private-proxy" not in json.dumps(document)
        configured = {
            **document["values"],
            "mode": "live",
            "chat_provider": "codex",
            "model": "fixture",
            "codex_reasoning_effort": "low",
        }
        assert client.put("/api/settings", json=configured).status_code == 200
        review = client.post(
            "/api/runs",
            json={
                "question": "How do checkpoints make human review durable?",
                "intent": "review",
            },
        ).json()
        assert review["status"] == "awaiting_review"
        assert review["mode"] == "live" and review["citations"]
        assert len(calls) == 1
        decision = client.post(f"/api/runs/{review['id']}/decision", json={"approved": True}).json()
        assert decision["status"] == "approved" and decision["answer"] == review["answer"]
        assert len(calls) == 1
    assert "fixture.exe" not in (tmp_path / "settings.json").read_text()
    assert "private-proxy" not in (tmp_path / "settings.json").read_text()


@pytest.mark.parametrize("proxy", [None, "http://operator:private-proxy@localhost:8080"])
def test_proxy_is_scoped_to_child_and_inherited_when_unset(proxy, monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://inherited.example:8080")
    monkeypatch.setenv("https_proxy", "http://lowercase.example:8080")
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1")
    original = os.environ.copy()

    def invoke(command, **kwargs):
        if proxy:
            environment = kwargs["env"]
            assert environment["HTTPS_PROXY"] == environment["https_proxy"] == proxy
            assert environment["HTTP_PROXY"] == environment["http_proxy"] == proxy
            assert environment["NO_PROXY"] == original["NO_PROXY"]
            assert proxy not in " ".join(command)
        else:
            assert kwargs["env"] is None
        return events()

    monkeypatch.setattr("repo_explorer.codex_model.subprocess.run", invoke)
    settings = Settings(_env_file=None, mode="live", model="fixture", codex_proxy_url=proxy)
    model = CodexChatModel(
        executable="fixture.exe", model_name="fixture", proxy_url=settings.codex_proxy_url
    )
    ChatAnswerGenerator(settings, model).generate("What happens?", "question", [], "")
    assert dict(os.environ) == original
    assert "private-proxy" not in model.model_dump_json()
    assert "private-proxy" not in settings.model_dump_json()
    assert "proxy_url" not in settings.public().model_dump_json()


@pytest.mark.parametrize(
    "proxy", ["localhost:8080", "http://localhost:99999", "https://proxy/path"]
)
def test_invalid_proxy_configuration_is_rejected(proxy):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, codex_proxy_url=proxy)


def test_proxy_reads_server_dotenv_but_cannot_be_set_in_public_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("REPO_EXPLORER_CODEX_PROXY_URL=http://localhost:8080\n")
    assert Settings().codex_proxy_url.get_secret_value() == "http://localhost:8080"
    with pytest.raises(ValidationError):
        WorkspaceConfig(codex_proxy_url="http://localhost:8080")


@pytest.mark.parametrize(
    "override", [{"base_url": "https://example.com"}, {"chat_api_key_env": "KEY"}]
)
def test_codex_does_not_silently_ignore_other_provider_credentials(override):
    with pytest.raises(ValidationError, match="CLI sign-in"):
        WorkspaceConfig(chat_provider="codex", **override)


def test_nonfatal_cli_diagnostic_does_not_hide_a_completed_response():
    diagnostic = json.dumps(
        {
            "type": "item.completed",
            "item": {
                "type": "error",
                "message": "Nonfatal startup warning",
            },
        }
    )
    answer, usage = parse_codex_events(diagnostic + "\n" + events().stdout)
    assert json.loads(answer)["citation_ids"] == ["S1"]
    assert usage["total_tokens"] == 115


def test_evaluation_preserves_safe_timeout_code():
    from repo_explorer.evaluation.live import safe_error

    error = CodexInvocationError("A safe timeout", code="timeout")
    assert safe_error("generation", error)["code"] == "timeout"


def test_script_wrapper_is_rejected_so_timeout_targets_native_process(tmp_path, monkeypatch):
    from repo_explorer.codex_model import resolve_codex_executable

    wrapper = tmp_path / "codex.exe"
    wrapper.write_text("#!/usr/bin/env node\n", encoding="utf-8")
    monkeypatch.setattr("repo_explorer.codex_model.shutil.which", lambda _: str(wrapper))
    with pytest.raises(ValueError, match="native CLI binary"):
        resolve_codex_executable()

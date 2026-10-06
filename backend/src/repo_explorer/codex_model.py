"""Local Codex CLI adapter for LangChain's structured chat-model boundary."""

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.outputs import ChatGeneration, ChatResult, Generation
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel, Field, SecretStr

# These controls target CLI 0.160.0. They are part of the adapter contract,
# not workspace preferences: changing them would change what evidence the model can use.
DISABLED_FEATURES = (
    "shell_tool",
    "unified_exec",
    "apps",
    "plugins",
    "hooks",
    "multi_agent",
    "browser_use",
    "browser_use_external",
    "computer_use",
    "code_mode",
    "code_mode_host",
    "memories",
    "skill_search",
    "skill_mcp_dependency_install",
    "image_generation",
    "view_image",
    "workspace_dependencies",
    "goals",
    "sleep_tool",
    "tool_suggest",
    "daemon_auto_start",
    "unbounded_connection_retries",
)


class CodexInvocationError(RuntimeError):
    """Safe public error; CLI stderr and prompts must never be included."""

    def __init__(self, message: str, code: str = "invalid_response", exit_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code


def resolve_codex_executable(configured: str = "") -> str:
    """Use a native executable; never route source/model text through a shell wrapper."""
    name = configured or ("codex.exe" if os.name == "nt" else "codex")
    executable = shutil.which(name)
    if not executable or (os.name == "nt" and Path(executable).suffix.lower() != ".exe"):
        raise ValueError(
            "Install a native Codex CLI or set REPO_EXPLORER_CODEX_EXECUTABLE on the server."
        )
    resolved = Path(executable).resolve()
    with resolved.open("rb") as handle:
        if handle.read(2) == b"#!":
            raise ValueError("Point REPO_EXPLORER_CODEX_EXECUTABLE at the native CLI binary.")
    return str(resolved)


def codex_version(executable: str) -> str:
    try:
        result = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("Could not check the configured Codex CLI version.") from None
    value = result.stdout.strip()
    if result.returncode or not re.fullmatch(r"codex-cli [0-9A-Za-z.+-]+", value):
        raise ValueError("The configured executable did not report a Codex CLI version.")
    return value


def parse_codex_events(output: str, *, exit_code: int | None = None) -> tuple[str, dict | None]:
    """Accept a completed text-only turn; reject failures and any observed tool activity."""
    answer, usage, completed = None, None, False
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            raise CodexInvocationError(
                "Codex returned an invalid event stream.", "invalid_event_stream", exit_code
            ) from None
        if not isinstance(event, dict):
            raise CodexInvocationError(
                "Codex returned an invalid event stream.", "invalid_event_stream", exit_code
            )
        kind = event.get("type")
        if not isinstance(kind, str):
            raise CodexInvocationError(
                "Codex returned an event without a valid type.", "invalid_event_stream", exit_code
            )
        if kind in {"error", "turn.failed"}:
            raise CodexInvocationError(
                "Codex reported a failed turn."
                if kind == "turn.failed"
                else "Codex reported an error in its event stream.",
                "turn_failed" if kind == "turn.failed" else "stream_error",
                exit_code,
            )
        if kind in {"item.started", "item.updated", "item.completed"}:
            item = event.get("item", {})
            if not isinstance(item, dict):
                raise CodexInvocationError(
                    "Codex returned an invalid event item.", "invalid_event_stream", exit_code
                )
            # Nonfatal CLI diagnostics use error items, separately from turn.failed.
            if not isinstance(item.get("type"), str):
                raise CodexInvocationError(
                    "Codex returned an item without a valid type.",
                    "invalid_event_stream",
                    exit_code,
                )
            if item["type"] not in {
                "agent_message",
                "reasoning",
                "error",
            }:
                raise CodexInvocationError(
                    "Codex attempted a tool action; the answer was rejected.",
                    "tool_activity",
                    exit_code,
                )
            if kind == "item.completed" and item["type"] == "agent_message":
                answer = item.get("text")
        if kind == "turn.completed":
            completed = True
            reported = event.get("usage")
            if reported is None:
                reported = {}
            if not isinstance(reported, dict):
                raise CodexInvocationError(
                    "Codex returned invalid usage metadata.", "invalid_usage", exit_code
                )
            if all(
                type(reported.get(key)) is int and reported[key] >= 0
                for key in ("input_tokens", "output_tokens")
            ):
                usage = {
                    "input_tokens": reported["input_tokens"],
                    "output_tokens": reported["output_tokens"],
                    "total_tokens": reported["input_tokens"] + reported["output_tokens"],
                }
                cached = reported.get("cached_input_tokens")
                if type(cached) is int and 0 <= cached <= reported["input_tokens"]:
                    usage["input_token_details"] = {"cache_read": cached}
    if exit_code:
        raise CodexInvocationError(
            "Codex exited unsuccessfully; check CLI sign-in, model access, and compatibility.",
            "cli_failed",
            exit_code,
        )
    if not completed:
        raise CodexInvocationError(
            "Codex returned no turn completion event.", "missing_completion", exit_code
        )
    if not isinstance(answer, str) or not answer.strip():
        raise CodexInvocationError(
            "Codex completed without a final answer.", "missing_answer", exit_code
        )
    return answer, usage


class CodexOutputParser(PydanticOutputParser):
    """Keep schema failures inspectable without exposing raw model output in errors."""

    def parse_result(self, result: list[Generation], *, partial: bool = False) -> BaseModel | None:
        try:
            return super().parse_result(result, partial=partial)
        except OutputParserException:
            raise CodexInvocationError(
                "Codex returned an answer that does not match the required schema.",
                code="invalid_structured_output",
            ) from None


class CodexChatModel(BaseChatModel):
    executable: str = Field(exclude=True)
    proxy_url: SecretStr | None = Field(default=None, exclude=True, repr=False)
    model_name: str
    timeout_seconds: float = Field(default=120, ge=1, le=300)
    reasoning_effort: str = "medium"
    cli_version: str = "unknown"

    @property
    def runtime_metadata(self) -> dict:
        return {"transport": "codex-cli", "cli_version": self.cli_version}

    @property
    def _llm_type(self) -> str:
        return "codex-cli"

    @property
    def _identifying_params(self) -> dict:
        return {"model_name": self.model_name, "reasoning_effort": self.reasoning_effort}

    def with_structured_output(self, schema: type[BaseModel], **kwargs: Any):
        if kwargs or not isinstance(schema, type) or not issubclass(schema, BaseModel):
            raise ValueError("Codex structured output requires a Pydantic response model.")
        strict_schema = convert_to_openai_tool(schema, strict=True)["function"]["parameters"]
        return self.bind(response_schema=strict_schema) | CodexOutputParser(pydantic_object=schema)

    def _generate(
        self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs: Any
    ) -> ChatResult:
        schema = kwargs.get("response_schema")
        if stop or not isinstance(schema, dict):
            raise ValueError("Codex generation requires structured output and no stop sequences.")
        if any(
            message.type not in {"system", "human"} or not isinstance(message.content, str)
            for message in messages
        ):
            raise ValueError("This adapter accepts text system/human messages only.")
        instructions = "\n\n".join(
            message.content for message in messages if message.type == "system"
        )
        prompt = "\n\n".join(message.content for message in messages if message.type == "human")
        # No repository, annotation files, parent chat, or project instructions in the working dir.
        with tempfile.TemporaryDirectory(prefix="repo-explorer-codex-") as directory:
            root = Path(directory)
            schema_path, instructions_path = root / "schema.json", root / "instructions.txt"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            instructions_path.write_text(instructions, encoding="utf-8")
            command = [
                self.executable,
                "exec",
                "--ignore-user-config",
                "--strict-config",
                "--ephemeral",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--json",
                "--color",
                "never",
                "--model",
                self.model_name,
                "--output-schema",
                str(schema_path),
            ]
            overrides = {
                "approval_policy": "never",
                "web_search": "disabled",
                "project_doc_max_bytes": 0,
                "memories.use_memories": False,
                "model_instructions_file": instructions_path.as_posix(),
                "model_reasoning_effort": self.reasoning_effort,
                "mcp_servers": {},
                "features.skip_host_skill_discovery": True,
                **{f"features.{feature}": False for feature in DISABLED_FEATURES},
            }
            for name, value in overrides.items():
                command.extend(["-c", f"{name}={json.dumps(value)}"])
            command.append("-")
            environment = None
            if self.proxy_url is not None:
                # Scope routing to this child; preserve inherited NO_PROXY bypass rules.
                environment = os.environ.copy()
                for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
                    environment[name] = self.proxy_url.get_secret_value()
            try:
                result = subprocess.run(
                    command,
                    input=prompt,
                    cwd=root,
                    env=environment,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.timeout_seconds,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            except subprocess.TimeoutExpired:
                raise CodexInvocationError(
                    "Codex generation exceeded the configured timeout.", code="timeout"
                ) from None
            except OSError:
                raise CodexInvocationError(
                    "The configured Codex executable could not run.", code="unavailable"
                ) from None
            content, usage = parse_codex_events(result.stdout, exit_code=result.returncode)
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content=content,
                        usage_metadata=usage,
                        response_metadata={"model_name": self.model_name, "provider": "codex-cli"},
                    )
                )
            ]
        )

"""BDD step implementations for entrypoint.feature.

Exercises the ``cpp-mcp`` console-script entry point via a raw subprocess +
low-level JSON-RPC message exchange over stdin/stdout (no MCP SDK client needed).
This directly tests C-10 / SC_C10_ENTRY: the installed console script must emit a
valid JSON-RPC frame on stdout and must not emit error lines to stderr before that
first frame.

Covers: US-M1/AC-1, C-10, SC_C10_ENTRY.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from pytest_bdd import given, scenarios, then, when

scenarios("features/entrypoint.feature")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VENV_SCRIPTS = Path(sys.executable).parent
_SCRIPT = _VENV_SCRIPTS / "cpp-mcp"

# JSON-RPC initialize request (MCP 2024-11-05 protocol)
_INITIALIZE_REQUEST = json.dumps(
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "0.0.1"},
        },
    }
)


def _build_stdio_input() -> bytes:
    """Return the raw bytes to send on stdin: length-prefixed JSON-RPC frame."""
    # FastMCP/MCP SDK uses newline-delimited JSON (NDJSON) over stdio — one JSON
    # object per line.
    return (_INITIALIZE_REQUEST + "\n").encode()


# ---------------------------------------------------------------------------
# Given
# ---------------------------------------------------------------------------


@given("cpp-mcp is installed as a console script")
def cpp_mcp_console_script_present(ctx: dict[str, Any]) -> None:
    """Verify the console script is available in the current venv and record path."""
    assert _SCRIPT.exists(), (
        f"cpp-mcp console script not found at {_SCRIPT}. Run 'uv pip install -e .' to install it."
    )
    ctx["script"] = str(_SCRIPT)


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------


@when("the cpp-mcp command is run with CPP_MCP_ALLOWED_ROOTS set and an initialize request is sent")
def run_cpp_mcp_with_initialize(tmp_path: Path, ctx: dict[str, Any]) -> None:
    """Spawn the cpp-mcp process, send an initialize request, and capture output."""
    allowed_root = tmp_path / "projects"
    allowed_root.mkdir()

    env = {**os.environ, "CPP_MCP_ALLOWED_ROOTS": str(allowed_root)}

    proc = subprocess.Popen(
        [ctx["script"]],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    stdin_bytes = _build_stdio_input()
    try:
        stdout_bytes, stderr_bytes = proc.communicate(
            input=stdin_bytes,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout_bytes, stderr_bytes = proc.communicate()

    ctx["stdout"] = stdout_bytes
    ctx["stderr"] = stderr_bytes
    ctx["returncode"] = proc.returncode


# ---------------------------------------------------------------------------
# Then
# ---------------------------------------------------------------------------


@then("a JSON-RPC response frame is received on stdout")
def assert_jsonrpc_frame_on_stdout(ctx: dict[str, Any]) -> None:
    """At least one valid JSON-RPC object must appear on stdout."""
    stdout_text = ctx["stdout"].decode("utf-8", errors="replace")
    lines = [line.strip() for line in stdout_text.splitlines() if line.strip()]
    assert lines, (
        f"No output on stdout. stderr was:\n{ctx['stderr'].decode('utf-8', errors='replace')}"
    )
    # The first non-empty line must be a valid JSON object
    first_line = lines[0]
    try:
        frame = json.loads(first_line)
    except json.JSONDecodeError as e:
        raise AssertionError(
            f"First stdout line is not valid JSON: {first_line!r}\nError: {e}"
        ) from e
    assert isinstance(frame, dict), f"Expected JSON object, got: {type(frame)}: {frame!r}"
    assert "jsonrpc" in frame, f"JSON-RPC frame missing 'jsonrpc' field: {frame}"


@then("stderr contains no error lines before the first stdout frame")
def assert_no_stderr_errors_before_first_frame(ctx: dict[str, Any]) -> None:
    """Stderr must not contain ERROR-level lines or Python tracebacks.

    INFO/DEBUG/WARNING log lines on stderr are acceptable (C-9 only forbids
    log output on *stdout*).  But ERROR lines or Python Traceback blocks
    before the server sends its first frame indicate a startup failure.
    """
    stderr_text = ctx["stderr"].decode("utf-8", errors="replace")
    lines = stderr_text.splitlines()

    # We check only lines that appear before a sensible startup message;
    # since we can't synchronise reliably, check the entire stderr output
    # for hard error signals.
    error_lines = [
        line
        for line in lines
        if line.strip().startswith("Traceback")
        or ("ERROR" in line and "INFO" not in line)  # avoid "INFORMATION" false positives
    ]
    assert not error_lines, (
        "stderr contains error lines that indicate a startup failure:\n" + "\n".join(error_lines)
    )

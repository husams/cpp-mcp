"""BDD step implementations for transport_stdio feature (Story 7 / US-14).

Uses the official MCP client (stdio_client + ClientSession) to spawn the server
subprocess and exercise it over stdin/stdout.

QA additions (over developer baseline):
  - SC_US_14_3 now asserts all 7 tools (including ingest_code).
  - SC_US_14_CALL_ENVELOPE: subprocess tools/call with path-traversal input
    must return a structured error envelope, not a raw MCP error or traceback.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from pytest_bdd import given, scenarios, then, when

scenarios("features/transport_stdio.feature")


# ---------------------------------------------------------------------------
# Background / Given
# ---------------------------------------------------------------------------


@given("the server subprocess is started in stdio mode with a temp allowed root")
def server_subprocess_ready(tmp_path: Path, ctx: dict[str, Any]) -> None:
    """Record the temp root; the actual subprocess is spawned inside the When step."""
    root = tmp_path / "projects"
    root.mkdir()
    ctx["allowed_root"] = str(root)


# ---------------------------------------------------------------------------
# When — initialize
# ---------------------------------------------------------------------------


@when("the client sends initialize")
def client_initialize(ctx: dict[str, Any]) -> None:
    import asyncio

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    allowed_root = ctx["allowed_root"]

    env = {**os.environ, "CPP_MCP_ALLOWED_ROOTS": allowed_root}

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "cpp_mcp"],
        env=env,
    )

    async def _run() -> dict[str, Any]:
        async with stdio_client(params) as (read, write), ClientSession(read, write) as client:
            init_result = await client.initialize()
            ctx["init_result"] = init_result
            return {"ok": True}

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# When — tools/list
# ---------------------------------------------------------------------------


@when("the client calls tools/list")
def client_list_tools(ctx: dict[str, Any]) -> None:
    import asyncio

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    allowed_root = ctx["allowed_root"]
    env = {**os.environ, "CPP_MCP_ALLOWED_ROOTS": allowed_root}

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "cpp_mcp"],
        env=env,
    )

    async def _run() -> None:
        async with stdio_client(params) as (read, write), ClientSession(read, write) as client:
            await client.initialize()
            tools_result = await client.list_tools()
            ctx["tools"] = [t.name for t in tools_result.tools]

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# When — tools/call (path-traversal → error envelope)
# ---------------------------------------------------------------------------


@when("the client calls get_definition with a path-traversal file_path")
def client_call_tool_path_violation(ctx: dict[str, Any]) -> None:
    """Dispatch a real tools/call over stdio and capture the raw result dict.

    The input intentionally uses a path-traversal file_path so that the
    server's wrap_tool decorator catches PathViolationError and returns a
    structured error envelope rather than a raw MCP error or Python traceback.
    """
    import asyncio

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    allowed_root = ctx["allowed_root"]
    env = {**os.environ, "CPP_MCP_ALLOWED_ROOTS": allowed_root}

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "cpp_mcp"],
        env=env,
    )

    async def _run() -> None:
        async with stdio_client(params) as (read, write), ClientSession(read, write) as client:
            await client.initialize()
            # call_tool returns a CallToolResult whose .content is a list of
            # ContentBlock objects.  For our tools, the first block's text is
            # the JSON-serialised dict returned by the handler.
            result = await client.call_tool(
                "get_definition",
                {"file_path": "../../etc/passwd", "line": 1, "col": 1},
            )
            ctx["call_result_raw"] = result

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Then — initialize assertions
# ---------------------------------------------------------------------------


@then("the initialize response is received successfully")
def assert_initialize_ok(ctx: dict[str, Any]) -> None:
    assert "init_result" in ctx, "initialize was not called or failed"
    assert ctx["init_result"] is not None


# ---------------------------------------------------------------------------
# Then — tools/list assertions (all 7 tools)
# ---------------------------------------------------------------------------


@then('the tools list contains "get_definition"')
def assert_has_get_definition(ctx: dict[str, Any]) -> None:
    assert "get_definition" in ctx["tools"], f"tools: {ctx['tools']}"


@then('the tools list contains "get_references"')
def assert_has_get_references(ctx: dict[str, Any]) -> None:
    assert "get_references" in ctx["tools"]


@then('the tools list contains "get_type_info"')
def assert_has_get_type_info(ctx: dict[str, Any]) -> None:
    assert "get_type_info" in ctx["tools"]


@then('the tools list contains "get_ast"')
def assert_has_get_ast(ctx: dict[str, Any]) -> None:
    assert "get_ast" in ctx["tools"]


@then('the tools list contains "get_header_info"')
def assert_has_get_header_info(ctx: dict[str, Any]) -> None:
    assert "get_header_info" in ctx["tools"]


@then('the tools list contains "get_preprocessor_state"')
def assert_has_get_preprocessor_state(ctx: dict[str, Any]) -> None:
    assert "get_preprocessor_state" in ctx["tools"]


@then('the tools list contains "ingest_code"')
def assert_has_export_to_graphdb(ctx: dict[str, Any]) -> None:
    """QA addition: Story 8 wired ingest_code — verify it appears over stdio."""
    assert "ingest_code" in ctx["tools"], (
        f"ingest_code missing from tools/list over stdio. Got: {ctx['tools']}"
    )


# ---------------------------------------------------------------------------
# Then — tools/call error envelope assertions (SC-US-14-CALL-ENVELOPE)
# ---------------------------------------------------------------------------


@then("the response is a structured error envelope")
def assert_call_result_is_envelope(ctx: dict[str, Any]) -> None:
    """The call result content must decode to a dict with the error envelope shape."""
    import json

    raw = ctx["call_result_raw"]
    # MCP SDK returns a CallToolResult; extract the text from the first content block.
    content_blocks = getattr(raw, "content", [])
    assert content_blocks, f"call_tool returned no content blocks: {raw!r}"

    first = content_blocks[0]
    text = getattr(first, "text", None)
    assert text is not None, f"First content block has no .text: {first!r}"

    try:
        envelope = json.loads(text)
    except json.JSONDecodeError as e:
        pytest.fail(f"call_tool response text is not valid JSON: {text!r} — {e}")

    ctx["call_envelope"] = envelope

    assert isinstance(envelope, dict), f"Expected dict envelope, got {type(envelope)}: {envelope!r}"
    assert "code" in envelope, f"Envelope missing 'code': {envelope}"


@then('the envelope code is "PATH_VIOLATION"')
def assert_envelope_code_path_violation(ctx: dict[str, Any]) -> None:
    envelope = ctx["call_envelope"]
    assert envelope.get("code") == "PATH_VIOLATION", (
        f"Expected code='PATH_VIOLATION', got code={envelope.get('code')!r}\n"
        f"Full envelope: {envelope}"
    )


@then('the envelope message does not contain "Traceback"')
def assert_no_traceback_in_message(ctx: dict[str, Any]) -> None:
    """US-13/AC-2: no Python traceback must leak to MCP callers."""
    envelope = ctx["call_envelope"]
    msg = envelope.get("message", "")
    assert "Traceback" not in msg, f"Python traceback leaked into error envelope message: {msg!r}"


@then("the envelope contains a request_id field")
def assert_envelope_has_request_id(ctx: dict[str, Any]) -> None:
    envelope = ctx["call_envelope"]
    assert "request_id" in envelope, (
        f"Envelope missing 'request_id' field. Got: {list(envelope.keys())}"
    )


# ---------------------------------------------------------------------------
# Inline import needed for pytest.fail inside a step
# ---------------------------------------------------------------------------
import pytest  # noqa: E402 — must follow BDD step definitions

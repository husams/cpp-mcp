"""S4: Verify wrap_tool suppresses internal detail from INTERNAL_ERROR responses.

SC_USM5_6 (US-M5/AC-4, EC-3): A tool function that raises a bare RuntimeError
must return an error envelope with no traceback text and no internal paths in
the message field.  FastMCP's mask_error_details=True is configured in
build_server() (app.py) as the server-level safety net; wrap_tool is the
outermost *function* decorator and must absorb exceptions before they reach
FastMCP's own serialization so the return value is always the dict envelope.
"""

from __future__ import annotations

from cpp_mcp.core.error_envelope import ErrorCode, wrap_tool

_INTERNAL_PATH = "/Users/husam/workspace/cpp-mcp/src/cpp_mcp/core/secret.py"
_TOOL_NAME = "cpp_get_definition"


class TestMaskErrorDetails:
    """SC_USM5_6: INTERNAL_ERROR response leaks no traceback or internal paths."""

    def test_runtime_error_becomes_internal_error(self) -> None:
        """Bare RuntimeError must map to INTERNAL_ERROR code."""

        @wrap_tool(_TOOL_NAME)
        def bad_tool() -> None:  # type: ignore[return]
            raise RuntimeError("unexpected failure")

        result = bad_tool()
        assert isinstance(result, dict)
        assert result["code"] == str(ErrorCode.INTERNAL_ERROR)

    def test_no_traceback_in_message(self) -> None:
        """INTERNAL_ERROR message must not contain Python traceback text."""

        @wrap_tool(_TOOL_NAME)
        def bad_tool() -> None:  # type: ignore[return]
            raise RuntimeError("Traceback (most recent call last): secret detail")

        result = bad_tool()
        assert "Traceback" not in result["message"]
        assert "secret detail" not in result["message"]

    def test_no_internal_path_in_message(self) -> None:
        """INTERNAL_ERROR message must not expose server-internal absolute paths."""

        @wrap_tool(_TOOL_NAME)
        def bad_tool() -> None:  # type: ignore[return]
            raise RuntimeError(f"failed in {_INTERNAL_PATH}")

        result = bad_tool()
        assert _INTERNAL_PATH not in result["message"]
        assert "/Users/husam" not in result["message"]

    def test_envelope_shape_on_internal_error(self) -> None:
        """INTERNAL_ERROR envelope has exactly {code, message, tool, request_id}."""

        @wrap_tool(_TOOL_NAME)
        def bad_tool() -> None:  # type: ignore[return]
            raise ValueError("db password is s3cr3t!")

        result = bad_tool()
        assert set(result.keys()) == {"code", "message", "tool", "request_id"}
        assert result["code"] == str(ErrorCode.INTERNAL_ERROR)
        assert "s3cr3t" not in result["message"]

    def test_mask_error_details_configured_in_server(self) -> None:
        """build_server() must configure FastMCP with mask_error_details=True (US-M5/AC-4)."""
        from cpp_mcp.server.app import build_server

        mcp = build_server()
        # FastMCP stores this as _mask_error_details on the server instance.
        assert getattr(mcp, "_mask_error_details", None) is True, (
            "FastMCP server must be constructed with mask_error_details=True"
        )

    def test_registered_tool_fn_returns_envelope_not_raises(self) -> None:
        """A registered tool's fn must return the error envelope rather than raise.

        This confirms wrap_tool absorbs exceptions before FastMCP sees them,
        so mask_error_details is a belt-and-suspenders safety net only.
        """

        @wrap_tool("test_tool")
        def broken_registered_fn() -> None:  # type: ignore[return]
            raise RuntimeError("unhandled")

        result = broken_registered_fn()
        assert isinstance(result, dict), (
            "wrap_tool must return a dict envelope, not re-raise the exception"
        )
        assert result["code"] == str(ErrorCode.INTERNAL_ERROR)

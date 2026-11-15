"""The API's single MCP session: one stdio server process for the app's lifetime.

The stdio client is built on anyio task groups, so it must be entered and
exited by the same task. `start()` and `stop()` are therefore called only from
the FastAPI lifespan, never per request.

Failure policy: fail fast. If the server cannot start, or a call fails or times
out, the caller gets `McpError` (mapped to a 503). There is no restart-and-retry:
a restart would have to happen inside the lifespan task, and a silent retry
could hide a crashing server.
"""

import logging
import os
import sys
import time
from contextlib import AsyncExitStack

from mcp import Client, StdioServerParameters

from support_copilot.api.contracts import ToolCall
from support_copilot.config import BACKEND_DIR

log = logging.getLogger("support_copilot.api.mcp")

CALL_TIMEOUT_S = 10.0


class McpError(Exception):
    """The MCP server is down, timed out, or rejected a call. `code` goes in the run record."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def default_server_params() -> StdioServerParameters:
    # sys.executable: the same interpreter (and venv) as the API, on any OS.
    # The full environment is passed so SUPPORT_COPILOT_DB reaches the child.
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "support_copilot.mcp_server"],
        cwd=str(BACKEND_DIR),
        env=dict(os.environ),
    )


class McpGateway:
    def __init__(self, params: StdioServerParameters | None = None):
        self._params = params or default_server_params()
        self._stack = AsyncExitStack()
        self._client: Client | None = None

    async def start(self) -> None:
        """Start the server process. A failure is logged, not raised: the ticket
        routes still work and assistant calls answer 503."""
        try:
            self._client = await self._stack.enter_async_context(
                Client(self._params, read_timeout_seconds=CALL_TIMEOUT_S)
            )
            log.info("MCP server started")
        except Exception:
            log.exception("MCP server failed to start")
            self._client = None

    async def stop(self) -> None:
        self._client = None
        await self._stack.aclose()

    async def ready(self) -> bool:
        if self._client is None:
            return False
        try:
            # A real round trip to the process (protocol `ping` no longer exists in SDK v2).
            await self._client.list_tools()
            return True
        except Exception:
            log.exception("MCP readiness check failed")
            return False

    async def call(self, tool: str, arguments: dict, trace: list[ToolCall]) -> dict:
        """Call one tool, append it to the trace, and return its structured result."""
        arguments = {k: v for k, v in arguments.items() if v is not None}
        started = time.perf_counter()
        ok = False
        try:
            if self._client is None:
                raise McpError("mcp_unavailable")
            try:
                result = await self._client.call_tool(tool, arguments)
            except Exception as exc:
                log.exception("MCP call %s failed", tool)
                raise McpError("mcp_unavailable") from exc
            if result.is_error or result.structured_content is None:
                # Arguments are validated by the API first, so this is a contract bug.
                log.error("MCP tool %s returned an error: %s", tool, result.content)
                raise McpError("mcp_tool_error")
            ok = True
            return result.structured_content
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            trace.append(ToolCall(tool=tool, arguments=arguments, ok=ok, duration_ms=duration_ms))

"""FastAPI app. Ticket reads/writes go straight to SQLite; every assistant
action goes through the MCP server (read-only) and the deterministic composer.

    uv run uvicorn support_copilot.api.main:app --reload
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from mcp import StdioServerParameters
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, selectinload

from support_copilot.api.assistant import TicketNotFound, limitations, run_action
from support_copilot.api.contracts import (
    AssistantRequest,
    AssistantResponse,
    Health,
    ReviewedUpdate,
    TicketDetail,
    TicketSummary,
    ToolCall,
)
from support_copilot.api.mcp_gateway import McpError, McpGateway
from support_copilot.config import db_url
from support_copilot.db.models import AssistantRun, Ticket
from support_copilot.schemas import Category, Priority, Status

log = logging.getLogger("support_copilot.api")

TicketIdPath = Annotated[str, Path(pattern=r"^T-\d{1,6}$")]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_app(mcp_params: StdioServerParameters | None = None) -> FastAPI:
    """`mcp_params` lets tests point the app at a different (or broken) server command."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = create_engine(db_url())
        app.state.mcp = McpGateway(mcp_params)
        await app.state.mcp.start()
        try:
            yield
        finally:
            await app.state.mcp.stop()
            app.state.engine.dispose()

    app = FastAPI(title="Support Copilot API", version="0.1.0", lifespan=lifespan)

    def db(request: Request):
        with Session(request.app.state.engine) as session:
            yield session

    Db = Annotated[Session, Depends(db)]

    # ---- errors: safe messages to the client, details to the log -------------

    @app.exception_handler(TicketNotFound)
    async def ticket_not_found(_: Request, exc: TicketNotFound):
        return JSONResponse(status_code=404, content={"detail": f"Ticket {exc} not found"})

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, exc: RequestValidationError):
        # FastAPI's default 422 echoes the submitted value back (`input`), which
        # can be a whole oversized query. Keep only where and what went wrong.
        errors = [
            {"loc": list(e["loc"]), "msg": e["msg"].removeprefix("Value error, "), "type": e["type"]}
            for e in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": errors})

    @app.exception_handler(McpError)
    async def mcp_unavailable(_: Request, exc: McpError):
        return JSONResponse(
            status_code=503,
            content={"detail": "The assistant's data service is unavailable. Please try again."},
        )

    # ---- routes --------------------------------------------------------------

    @app.get("/health", response_model=Health)
    async def health(request: Request):
        try:
            with request.app.state.engine.connect() as conn:
                conn.execute(text("SELECT 1 FROM tickets LIMIT 1"))
            database = True
        except Exception:
            log.exception("database health check failed")
            database = False
        mcp_ready = await request.app.state.mcp.ready()
        return Health(status="ok" if database and mcp_ready else "degraded", database=database, mcp_ready=mcp_ready)

    @app.get("/api/tickets", response_model=list[TicketSummary])
    def list_tickets(
        session: Db,
        status: Status | None = None,
        priority: Priority | None = None,
        category: Category | None = None,
    ):
        query = select(Ticket).order_by(Ticket.id)
        if status:
            query = query.where(Ticket.status == status)
        if priority:
            query = query.where(Ticket.priority == priority)
        if category:
            query = query.where(Ticket.category == category)
        return session.scalars(query).all()

    def _load_ticket(session: Session, ticket_id: str) -> Ticket:
        ticket = session.get(Ticket, ticket_id, options=[selectinload(Ticket.messages)])
        if ticket is None:
            raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
        return ticket

    @app.get("/api/tickets/{ticket_id}", response_model=TicketDetail)
    def get_ticket(ticket_id: TicketIdPath, session: Db):
        return _load_ticket(session, ticket_id)

    @app.patch("/api/tickets/{ticket_id}/reviewed", response_model=TicketDetail)
    def set_reviewed(ticket_id: TicketIdPath, body: ReviewedUpdate, session: Db):
        ticket = _load_ticket(session, ticket_id)
        ticket.reviewed_at = _now() if body.reviewed else None
        session.commit()
        return ticket

    @app.post("/api/assistant/run", response_model=AssistantResponse)
    async def run_assistant(body: AssistantRequest, request: Request):
        run_id = str(uuid.uuid4())
        trace: list[ToolCall] = []
        started = time.perf_counter()
        answer = retrieval = None
        error_code = None
        try:
            answer, retrieval = await run_action(body, request.app.state.mcp, trace)
        except TicketNotFound:
            error_code = "ticket_not_found"
            raise
        except McpError as exc:
            error_code = exc.code
            raise
        except Exception:
            error_code = "internal_error"
            raise
        finally:
            # Every run is recorded, success or failure. Metadata only: no query or ticket text.
            with Session(request.app.state.engine) as session:
                session.add(
                    AssistantRun(
                        id=run_id,
                        created_at=_now(),
                        action=body.action,
                        ticket_id=body.ticket_id,
                        tools=[call.tool for call in trace],
                        retrieval_method=retrieval.method if retrieval else None,
                        answer_state=answer.state if answer else None,
                        success=error_code is None,
                        error_code=error_code,
                        duration_ms=round((time.perf_counter() - started) * 1000),
                    )
                )
                session.commit()
        return AssistantResponse(
            run_id=run_id,
            answer=answer,
            retrieval=retrieval,
            tool_trace=trace,
            limitations=limitations(body.action),
        )

    return app


app = create_app()

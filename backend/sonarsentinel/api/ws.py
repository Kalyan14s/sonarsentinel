"""Job event stream ``/ws/jobs/{job_id}`` (ST-083, ADR-018 §1).

Protocol: server messages are ``{type, job_id, seq, ts, ...}``. The client may send
``{"type": "resume", "after_seq": N}`` as its first message (the server waits up to 0.5 s) and
``{"type": "ping"}`` at any time (answer: ``{"type": "pong", job_id, ts}`` without ``seq``). The
server replays buffered or logged events after ``after_seq``, then tails new ones; an event is
never sent twice (``seq`` must grow). After ``done`` or ``error`` the socket closes with 1000; an
unknown job gets an ``error`` message and close code 4404.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool

from sonarsentinel.api.context import ApiContext, get_context
from sonarsentinel.report.builder import now_utc
from sonarsentinel.storage.models import Job
from sonarsentinel.storage.repository import FINISHED_STATUSES

router = APIRouter()

TERMINAL_EVENTS = frozenset({"done", "error"})
FIRST_MESSAGE_TIMEOUT_S = 0.5
IDLE_CHECK_S = 1.0
CLOSE_NORMAL = 1000
CLOSE_NOT_FOUND = 4404

Message = dict[str, Any]
Sender = Callable[[Message], Awaitable[None]]


def _job_status(context: ApiContext, job_id: str) -> str | None:
    with context.database.session() as session:
        job = session.get(Job, job_id)
        return job.status if job is not None else None


def pong(job_id: str) -> Message:
    return {"type": "pong", "job_id": job_id, "ts": now_utc()}


async def _read_client(websocket: WebSocket, job_id: str, send: Sender) -> None:
    """Answer pings until the client goes away."""
    try:
        while True:
            message = await websocket.receive_json()
            if isinstance(message, dict) and message.get("type") == "ping":
                await send(pong(job_id))
    except Exception:  # disconnect, closed socket or malformed JSON: stop reading
        return


async def first_message(websocket: WebSocket) -> Message | None:
    """The client's opening message, if one arrives within the timeout."""
    try:
        message = await asyncio.wait_for(websocket.receive_json(), FIRST_MESSAGE_TIMEOUT_S)
    except TimeoutError:
        return None
    return message if isinstance(message, dict) else None


def resume_after(message: Message | None) -> int:
    if message is None or message.get("type") != "resume":
        return 0
    try:
        return max(0, int(message.get("after_seq") or 0))
    except (TypeError, ValueError):
        return 0


@router.websocket("/ws/jobs/{job_id}")
async def job_events(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    context = get_context(websocket.app)
    if await run_in_threadpool(_job_status, context, job_id) is None:
        await websocket.send_json(
            {
                "type": "error",
                "job_id": job_id,
                "ts": now_utc(),
                "code": "NOT_FOUND",
                "message": f"Job {job_id} not found",
            }
        )
        await websocket.close(code=CLOSE_NOT_FOUND)
        return

    loop = asyncio.get_running_loop()
    events: asyncio.Queue[Message] = asyncio.Queue()
    send_lock = asyncio.Lock()

    def listener(event: Message) -> None:  # called on the job worker thread
        if event.get("job_id") == job_id:
            loop.call_soon_threadsafe(events.put_nowait, event)

    async def send(message: Message) -> None:
        async with send_lock:
            await websocket.send_json(message)

    context.jobs.add_listener(listener)  # before the replay snapshot, so nothing falls between
    reader: asyncio.Task[None] | None = None
    try:
        opening = await first_message(websocket)
        if opening is not None and opening.get("type") == "ping":
            await send(pong(job_id))
        last = resume_after(opening)
        reader = asyncio.create_task(_read_client(websocket, job_id, send))

        async def deliver(event: Message) -> bool:
            """Send unless already sent; True once the terminal event went out."""
            nonlocal last
            seq = int(event.get("seq", 0))
            if seq <= last:
                return False
            await send(event)
            last = seq
            return event.get("type") in TERMINAL_EVENTS

        for event in await run_in_threadpool(context.jobs.replay, job_id, last):
            if await deliver(event):
                await websocket.close(code=CLOSE_NORMAL)
                return
        while True:
            try:
                event = await asyncio.wait_for(events.get(), IDLE_CHECK_S)
            except TimeoutError:
                if reader.done():
                    return  # the client disconnected
                status = await run_in_threadpool(_job_status, context, job_id)
                if status in FINISHED_STATUSES and events.empty():
                    for late in await run_in_threadpool(context.jobs.replay, job_id, last):
                        if await deliver(late):
                            break
                    await websocket.close(code=CLOSE_NORMAL)
                    return
                continue
            if await deliver(event):
                await websocket.close(code=CLOSE_NORMAL)
                return
    except (WebSocketDisconnect, RuntimeError):
        return
    finally:
        context.jobs.remove_listener(listener)
        if reader is not None:
            reader.cancel()

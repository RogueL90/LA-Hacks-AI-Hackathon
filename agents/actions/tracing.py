"""Call Kenil's observability hooks when that package is installed.

Until then, handlers still run and failures are logged as AgentError.
"""

from __future__ import annotations

import inspect
import logging
from functools import wraps
from typing import Any, Callable

log = logging.getLogger("lmh.actions")


def traced_agent(agent_name: str, step: str) -> Callable:
    try:
        from observability import traced_agent as real_traced_agent
    except ImportError:
        real_traced_agent = None

    if real_traced_agent is not None:
        return real_traced_agent(agent_name, step)

    def deco(fn: Callable) -> Callable:
        @wraps(fn)
        async def wrapper(ctx: Any, sender: str, msg: Any) -> Any:
            try:
                return await fn(ctx, sender, msg)
            except Exception as exc:
                payload = msg.model_dump() if hasattr(msg, "model_dump") else {}
                await report_error(
                    ctx,
                    getattr(msg, "job_id", ""),
                    agent_name,
                    step,
                    exc,
                    True,
                    payload,
                )
                raise

        return wrapper

    return deco


async def report_error(
    ctx: Any,
    job_id: str,
    agent: str,
    step: str,
    exc: BaseException,
    retryable: bool,
    retry_payload: dict,
) -> None:
    try:
        from observability import report_error as real_report_error
    except ImportError:
        real_report_error = None

    if real_report_error is not None:
        result = real_report_error(
            ctx, job_id, agent, step, exc, retryable, retry_payload
        )
        if inspect.isawaitable(result):
            await result
        return

    log.error(
        "AgentError agent=%s step=%s job_id=%s retryable=%s message=%s payload=%s",
        agent,
        step,
        job_id,
        retryable,
        exc,
        retry_payload,
    )

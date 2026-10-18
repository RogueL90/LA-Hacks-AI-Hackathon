"""Run one request against an agent inside a local Bureau."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from typing import Callable

from uagents import Agent, Bureau, Context


def run_bureau(service: Agent, request, response_model, check: Callable, timeout_s: float = 20) -> None:
    tester = Agent(
        name=f"{service.name}-tester",
        seed=f"{service.name}-tester-local-seed",
        port=9100 + (abs(hash(service.name)) % 200),
        mailbox=False,
    )

    @tester.on_event("startup")
    async def startup(ctx: Context) -> None:
        await asyncio.sleep(0.4)
        await ctx.send(service.address, request)

    @tester.on_message(response_model)
    async def on_result(ctx: Context, sender: str, msg) -> None:
        print(json.dumps(msg.model_dump(), indent=2), flush=True)
        try:
            check(msg)
        except Exception as exc:
            print(f"CHECK FAILED: {exc}")
            os._exit(1)
        os._exit(0)

    def watchdog() -> None:
        time.sleep(timeout_s)
        print("CHECK FAILED: bureau timed out")
        os._exit(1)

    threading.Thread(target=watchdog, daemon=True).start()
    bureau = Bureau()
    bureau.add(service)
    bureau.add(tester)
    bureau.run()

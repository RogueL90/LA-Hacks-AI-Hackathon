"""Send outgoing messages concurrently (uagents 0.26 sends them one at a time).

uagents' Dispenser posts every outgoing envelope of every agent in a Bureau through one
queue, one HTTP request at a time, and each request may wait up to aiohttp's 5-minute
default. One slow endpoint (or just many users) then delays every reply and agent hand-off
behind it; under load the chain tests saw "Timeout waiting for dispense response" and an
88 s wait for a reply that needs no work.

This keeps uagents' own send code and changes only the scheduling: envelopes to different
destinations or sessions go out in parallel, while envelopes for the same destination and
session keep their order (a payment request must arrive before its card). Each send is
capped so a dead endpoint can't hold its conversation for minutes.

Import and call apply() before starting agents (run/bureau.py does).
"""
import asyncio
from collections import defaultdict

from uagents.communication import Dispenser
from uagents_core.types import DeliveryStatus, MsgStatus

MAX_IN_FLIGHT = 64
SEND_TIMEOUT_S = 20


async def _run(self: Dispenser) -> None:
    gate = asyncio.Semaphore(MAX_IN_FLIGHT)
    # One lock per (destination, session): tasks are created in queue order and take the
    # lock as their first step, and asyncio.Lock wakes waiters first-in first-out.
    order: dict[tuple, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def deliver(env, endpoints, future, sync):
        key = (env.target, str(env.session))
        async with order[key]:
            async with gate:
                try:
                    await asyncio.wait_for(self._process_envelope(env, endpoints, future, sync), SEND_TIMEOUT_S)
                except asyncio.TimeoutError:
                    if not future.done():  # report it like any failed delivery, not as an exception
                        future.set_result(MsgStatus(
                            status=DeliveryStatus.FAILED, detail=f"No answer in {SEND_TIMEOUT_S} s",
                            destination=env.target, endpoint=endpoints[0] if endpoints else "", session=env.session))

    tasks: set[asyncio.Task] = set()
    try:
        while True:
            item = await self._envelopes.get()
            task = asyncio.get_running_loop().create_task(deliver(*item))
            tasks.add(task)
            task.add_done_callback(tasks.discard)
    except (asyncio.CancelledError, KeyboardInterrupt):
        # Let messages already handed over finish (as uagents does on shutdown).
        if tasks:
            await asyncio.wait(tasks, timeout=SEND_TIMEOUT_S)


def apply() -> None:
    Dispenser.run = _run

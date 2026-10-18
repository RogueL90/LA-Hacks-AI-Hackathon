"""Shared Claude plumbing for the extraction passes (plan.py, extract.py).

One structured-output call: images first, instructions last, parsed into a pydantic
model. Uses ANTHROPIC_MODEL with server-side refusal fallbacks.
"""
import base64
import io
import time
from typing import Optional, Type, TypeVar

from PIL import Image
from pydantic import BaseModel

from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

LLM_TIMEOUT_S = 90.0  # per call; keeps a build near the 120 s budget
LLM_MAX_TOKENS = 16000

T = TypeVar("T", bound=BaseModel)


def image_b64(path: str, max_px: int) -> str:
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_px, max_px))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85)
        return base64.standard_b64encode(buf.getvalue()).decode("ascii")


def frame_blocks(frames: list[tuple[int, dict]], max_px: int) -> list[dict]:
    """[(frame_index, frame)] -> alternating "Frame i" labels and image blocks."""
    content: list[dict] = []
    for i, frame in frames:
        ts = frame.get("timestamp_s")
        content.append({"type": "text", "text": f"Frame {i}" + (f" (t={ts:.0f}s)" if ts is not None else "")})
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64(frame["path"], max_px)},
        })
    return content


def parse(content: list[dict], schema: Type[T], effort: str, stats: Optional[dict] = None, retries: int = 0) -> T:
    """Runs one structured-output request and returns the parsed model.

    retries=0 for the single big call (a retried timeout would blow the build budget);
    the parallel per-room calls pass a few so a 429 doesn't kill the build.
    """
    import anthropic

    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set (space_service/.env)")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=LLM_TIMEOUT_S, max_retries=retries)

    t0 = time.perf_counter()
    response = client.beta.messages.parse(
        model=ANTHROPIC_MODEL,
        max_tokens=LLM_MAX_TOKENS,
        messages=[{"role": "user", "content": content}],
        output_format=schema,
        output_config={"effort": effort},
        # On a safety decline, the API re-runs the request on a fallback model in the same call.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if stats is not None:
        stats.update({
            "llm_s": round(time.perf_counter() - t0, 2),
            "model": response.model,
            "effort": effort,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "stop_reason": response.stop_reason,
        })
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to analyze these frames")
    if response.stop_reason == "max_tokens":
        raise RuntimeError(f"Claude ran out of output tokens ({LLM_MAX_TOKENS}); try fewer frames")
    if response.parsed_output is None:
        raise RuntimeError("Claude returned no parseable answer")
    return response.parsed_output

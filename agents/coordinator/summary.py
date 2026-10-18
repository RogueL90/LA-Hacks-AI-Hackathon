"""The wrap-up after an order: what was checked, what was ordered (with store links), next steps,
and the 3D view. Claude writes the next steps from the real findings and order; if that call fails
or is slow, a plain summary built from the same data goes out instead, so the message always arrives.
"""
import os

from shared.models import CartResult, ModeResult

MODEL = os.getenv("SUMMARY_MODEL", "claude-sonnet-5-5")  # quick: this goes out right after the payment
TIMEOUT_S = 15

PROMPT = """You write the last message of a home-safety service, right after the user paid for a demo order.
Write 3 to 5 short bullet points of practical next steps, most important first. Use only the facts below.
- Say what to install or do first and why (the most serious findings first).
- Include fixes that need no purchase (moving furniture, clearing a path) as steps.
- Mention fixes left out of the order, if any, and that they can be added later.
- Each bullet is one or two short sentences, under 30 words. Plain language, no headings, no links, no prices.
  Each bullet starts with "- ".

Check: {mode}. {summary}
Findings (severity 5 = critical):
{findings}
Ordered: {ordered}
Left out of the order: {left_out}"""


def _finding_lines(result: ModeResult) -> list[str]:
    return [f"- [{f.severity}] {f.title}: {f.fix_summary or ''}" for f in result.findings[:12]]


def fallback_steps(result: ModeResult, cart: CartResult | None, notes: dict) -> list[str]:
    """Next steps without Claude: install what was ordered by severity, then the no-purchase fixes."""
    ordered_ids = {q.finding_id for q in (cart.items if cart else []) if q.finding_id}
    steps = []
    ranked = sorted(result.findings, key=lambda f: -f.severity)
    first = [f for f in ranked if f.id in ordered_ids][:2]
    if first:
        steps.append("When the products arrive, start with " + " and ".join(f.title.lower() for f in first) + ".")
    free = [f for f in ranked if not f.product_query and f.fix_summary][:2]
    for f in free:
        steps.append(f"No purchase needed: {f.fix_summary[0].lower() + f.fix_summary[1:]}.")
    if notes.get("left_out"):
        steps.append("Left out to stay within budget, add later: " + "; ".join(notes["left_out"]).lower() + ".")
    steps.append("Open the 3D view and click each marker to see why it was flagged.")
    return [f"- {s}" for s in steps]


async def next_steps(result: ModeResult, cart: CartResult | None, notes: dict) -> list[str]:
    try:
        import anthropic

        prompt = PROMPT.format(
            mode=result.mode, summary=result.summary,
            findings="\n".join(_finding_lines(result)),
            ordered="; ".join(q.title for q in (cart.items if cart else [])) or "nothing",
            left_out="; ".join(notes.get("left_out") or []) or "nothing")
        client = anthropic.AsyncAnthropic(timeout=TIMEOUT_S, max_retries=0)
        response = await client.messages.create(
            model=MODEL, max_tokens=600, messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "low"})
        text = "".join(getattr(b, "text", "") for b in response.content).strip()
        lines = [l.strip() for l in text.splitlines() if l.strip().startswith("- ")]
        if response.stop_reason != "refusal" and 2 <= len(lines) <= 6:
            return lines
    except Exception:
        pass
    return fallback_steps(result, cart, notes)


async def wrap_up(result: ModeResult, cart: CartResult | None, notes: dict, total: str, viewer_url: str | None,
                  short) -> str:
    """The final message: summary, what was ordered with store links, next steps, 3D view."""
    items = cart.items if cart else []
    ordered = "\n".join(
        f"- [{short(q.title)}]({q.url}): ${q.price_usd:,.2f}"
        + (f" × {int((q.specs or {}).get('quantity', 1))}" if int((q.specs or {}).get("quantity", 1) or 1) > 1 else "")
        + f" at {q.merchant}" for q in items[:10])
    steps = "\n".join(await next_steps(result, cart, notes))
    parts = [
        f"**Order placed (demo):** {len(items)} product{'s' if len(items) != 1 else ''}, {total} paid in Stripe test "
        "mode. Nothing is really charged or shipped; in a real deployment I'd place these orders with each store.",
        f"**Summary:** {result.summary}",
        f"**What you ordered:**\n{ordered}" if ordered else "",
        f"**Next steps:**\n{steps}",
        f"**[Open your home in 3D]({viewer_url})**: every finding is pinned on its object." if viewer_url else "",
    ]
    return "\n\n".join(p for p in parts if p)

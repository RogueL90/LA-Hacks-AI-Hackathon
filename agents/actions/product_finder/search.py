"""Find real products, verify their pages, and keep the ones that fit."""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import httpx

from shared.models import FindProductsRequest, FindProductsResult, ProductQuery, ProductQuote

CACHE_PATH = Path(
    os.environ.get(
        "PRODUCT_FINDER_CACHE",
        str(Path(__file__).resolve().parent / "cache" / "queries.json"),
    )
)
SEARCH_BUDGET_S = 30
PAGE_TIMEOUT_S = 8
SEARCH_CONCURRENCY = 24

_chaos_used = False
_cache_lock = threading.Lock()


class ChaosFailure(RuntimeError):
    """One forced failure for the Recovery demo."""


def chaos_tripped() -> bool:
    global _chaos_used
    if os.getenv("CHAOS_PRODUCT_FINDER") == "1" and not _chaos_used:
        _chaos_used = True
        return True
    return False


def _cache_load() -> dict:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text())
    except json.JSONDecodeError:
        return {}


def _cache_save(data: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(data, indent=2))


def _cache_store(query: str, quotes: list[ProductQuote]) -> None:
    with _cache_lock:
        data = _cache_load()
        data[query] = [quote.model_dump() for quote in quotes]
        _cache_save(data)


def _as_float(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    if not match:
        return None
    return float(match.group(0))


def _limit_float(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return float(text)
    return None


def assess_fit(specs: dict, constraints: dict) -> tuple[bool, str]:
    """Constraints are maximums for numbers and exact matches for text."""
    if not constraints:
        return True, "no size constraints on this query"
    notes: list[str] = []
    fits = True
    for key, limit in constraints.items():
        if key in {"finding_id", "quantity", "room", "brand", "model", "age_years"}:
            continue
        actual = specs.get(key)
        limit_num = _limit_float(limit)
        if limit_num is not None:
            got = _as_float(actual)
            if got is None:
                fits = False
                notes.append(f"{key} is not listed on the product")
                continue
            if got <= limit_num + 1e-6:
                notes.append(f"{key} {got:g} fits the {limit_num:g} maximum")
            else:
                fits = False
                notes.append(f"{key} {got:g} is over the {limit_num:g} maximum")
            continue
        wanted = str(limit).strip().lower()
        got_text = "" if actual is None else str(actual).strip().lower()
        if not got_text:
            fits = False
            notes.append(f"{key} is not listed on the product")
        elif wanted == got_text or wanted in got_text:
            notes.append(f"{key} matches {limit}")
        else:
            fits = False
            notes.append(f"{key} is {actual}, needed {limit}")
    return fits, "; ".join(notes)


def choose_for_query(query: ProductQuery, candidates: list[ProductQuote]) -> list[ProductQuote]:
    """Cheapest verified fit, plus one verified backup that also fits."""
    today = date.today().isoformat()
    fitting: list[ProductQuote] = []
    for quote in candidates:
        if not quote.url_verified:
            continue
        if query.max_price_usd is not None and quote.price_usd > query.max_price_usd:
            continue
        specs = dict(quote.specs or {})
        fits, note = assess_fit(specs, query.constraints or {})
        if not fits:
            continue
        specs["quantity"] = query.quantity
        specs["query"] = query.query
        specs["price_as_of"] = specs.get("price_as_of") or today
        finding_id = quote.finding_id
        raw_finding = (query.constraints or {}).get("finding_id")
        if finding_id is None and isinstance(raw_finding, str):
            finding_id = raw_finding
        fitting.append(
            quote.copy(
                update={
                    "specs": specs,
                    "fit_note": f"Prices as of {specs['price_as_of']}. {note}",
                    "finding_id": finding_id,
                }
            )
        )
    fitting.sort(key=lambda quote: quote.price_usd)
    chosen: list[ProductQuote] = []
    if fitting:
        primary = fitting[0].copy(update={"specs": {**fitting[0].specs, "role": "primary"}})
        chosen.append(primary)
    if len(fitting) > 1:
        backup = fitting[1].copy(update={"specs": {**fitting[1].specs, "role": "backup"}})
        chosen.append(backup)
    return chosen


def _extract_json_array(text: str) -> list[dict]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", cleaned)
        if not match:
            return []
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
    if isinstance(parsed, dict):
        parsed = parsed.get("products") or parsed.get("candidates") or []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or "unknown"


def _candidate_from_raw(raw: dict) -> ProductQuote | None:
    url = str(raw.get("url") or "").strip()
    title = str(raw.get("title") or "").strip()
    price = _as_float(raw.get("price_usd"))
    if not title or not url.startswith(("http://", "https://")) or price is None or price <= 0:
        return None
    merchant = str(raw.get("merchant") or "").strip() or _host(url)
    specs = raw.get("specs") if isinstance(raw.get("specs"), dict) else {}
    image = raw.get("image_url")
    return ProductQuote(
        title=title,
        url=url,
        merchant=merchant,
        price_usd=round(price, 2),
        image_url=str(image) if image else None,
        specs=specs,
        url_verified=False,
    )


def _message_text(response) -> str:
    parts = []
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text.strip():
            parts.append(text)
    return "\n".join(parts)


def _anthropic_text(prompt: str, search: bool) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-5"
    kwargs = {
        "model": model,
        "max_tokens": 800,
        "messages": [{"role": "user", "content": prompt}],
    }
    if search:
        kwargs["tools"] = [
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 1,
            }
        ]
    response = client.messages.create(**kwargs)
    return _message_text(response)


def search_candidates(query: ProductQuery) -> list[ProductQuote]:
    prompt = (
        "Do one web search, then return ONLY a JSON array of 2 products currently for sale.\n"
        f"Query: {query.query}\n"
        f"Maximum price USD: {query.max_price_usd if query.max_price_usd is not None else 'none'}\n"
        f"Constraints (numbers are maximums the product must be within): {json.dumps(query.constraints)}\n"
        "Each object must have title, url, merchant, price_usd as a number, image_url, and specs. "
        "Put measured attributes such as length_in, width_m, or toilet_shape inside specs when the page states them.\n"
        "Use https URLs of real product pages. No markdown and no prose."
    )
    text = _anthropic_text(prompt, search=True)
    rows = _extract_json_array(text)
    quotes = []
    for raw in rows[:2]:
        quote = _candidate_from_raw(raw)
        if quote is not None:
            quotes.append(quote)
    return quotes


def _title_matches(title: str, page: str) -> bool:
    words = [word for word in re.findall(r"[a-z0-9]+", title.lower()) if len(word) > 3]
    if not words:
        return False
    hits = sum(1 for word in words if word in page)
    needed = 1 if len(words) < 3 else max(2, len(words) // 2)
    return hits >= needed


def _price_matches(price: float, page: str) -> bool:
    cents = f"{price:.2f}"
    whole = str(int(price)) if abs(price - int(price)) < 0.001 else None
    if cents in page or cents.replace(".", "") in page:
        return True
    return bool(whole and re.search(rf"\b{re.escape(whole)}\b", page))


_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


async def _page_text(client: httpx.AsyncClient, url: str, headers: dict | None) -> str:
    try:
        response = await client.get(url, headers=headers)
    except (httpx.HTTPError, UnicodeDecodeError):
        return ""
    if response.status_code >= 400:
        return ""
    return response.text[:250_000].lower()


async def verify_quote(client: httpx.AsyncClient, quote: ProductQuote) -> ProductQuote:
    page = await _page_text(client, quote.url, _BROWSER_HEADERS)
    if page and (_title_matches(quote.title, page) or _price_matches(quote.price_usd, page)):
        return quote.copy(update={"url_verified": True})
    return quote


async def resolve_query(client: httpx.AsyncClient, query: ProductQuery) -> tuple[list[ProductQuote], str | None]:
    cache = _cache_load()
    cached = cache.get(query.query)
    if isinstance(cached, list) and cached:
        loaded = [ProductQuote.model_validate(item) for item in cached]
        return loaded, None

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    raw_quotes = await asyncio.to_thread(search_candidates, query)
    checked = await asyncio.gather(*[verify_quote(client, quote) for quote in raw_quotes])
    verified = [quote for quote in checked if quote.url_verified]
    chosen = choose_for_query(query, verified)
    if chosen:
        _cache_store(query.query, chosen)
        return chosen, None
    return [], f"no verified products for: {query.query}"


async def find_products(request: FindProductsRequest) -> FindProductsResult:
    if chaos_tripped():
        raise ChaosFailure("CHAOS_PRODUCT_FINDER forced one failure")

    quotes: list[ProductQuote] = []
    notes: list[str] = []
    headers = _BROWSER_HEADERS
    limits = httpx.Limits(max_connections=60, max_keepalive_connections=30)
    gate = asyncio.Semaphore(SEARCH_CONCURRENCY)

    async def _one(query: ProductQuery) -> tuple[list[ProductQuote], str | None]:
        try:
            async with gate:
                return await asyncio.wait_for(resolve_query(client, query), timeout=SEARCH_BUDGET_S)
        except asyncio.TimeoutError:
            return [], f"timed out on: {query.query}"

    async with httpx.AsyncClient(timeout=PAGE_TIMEOUT_S, follow_redirects=True, headers=headers, limits=limits) as client:
        results = await asyncio.gather(*[_one(query) for query in request.queries])
    for found, note in results:
        quotes.extend(found)
        if note:
            notes.append(note)
    return FindProductsResult(
        job_id=request.job_id,
        ok=True,
        quotes=quotes,
        error="; ".join(notes) or None,
    )

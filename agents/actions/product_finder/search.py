"""Find real products, verify their pages, and keep the ones that fit."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import httpx

from shared.models import FindProductsRequest, FindProductsResult, ProductQuery, ProductQuote

log = logging.getLogger("lmh.product_finder")

CACHE_PATH = Path(
    os.environ.get(
        "PRODUCT_FINDER_CACHE",
        str(Path(__file__).resolve().parent / "cache" / "queries.json"),
    )
)
SEARCH_BUDGET_S = 30
PAGE_TIMEOUT_S = 6
PAGE_READ_CHARS = 1_500_000
PAGE_DEADLINE_S = 7
SEARCH_CONCURRENCY = 24
# One Claude call with web search per query. It must leave time for the page checks inside
# SEARCH_BUDGET_S, so it has its own timeout and no retries.
LLM_TIMEOUT_S = 22
DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 3000
CANDIDATES = 4
# Stores that answer bots with 403/429/503 or a captcha page even when the product is real.
BLOCKED_STATUS = {401, 403, 405, 429, 503}
BOT_WALL_WORDS = ("captcha", "robot check", "are you a human", "access denied", "verify you are human", "unusual traffic")

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


def _model() -> str:
    return os.environ.get("PRODUCT_FINDER_MODEL") or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL


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


_NOT_SPECS = {"finding_id", "quantity", "room", "brand", "model", "age_years"}


def _spec_key(key: str) -> str:
    """Constraints name the spec they limit ("width_in"); "max_width_in" means the same thing."""
    return key[4:] if key.startswith("max_") else key


def _fit(specs: dict, constraints: dict) -> tuple[bool | None, str]:
    """True when every constraint is confirmed, None when some aren't listed, False when one fails.

    Constraints are maximums for numbers and matches for text. A product page that doesn't
    list an attribute isn't proof it doesn't fit, so it stays in with a note to check.
    """
    if not constraints:
        return True, "no size constraints on this query"
    notes: list[str] = []
    status: bool | None = True
    for raw_key, limit in constraints.items():
        if raw_key in _NOT_SPECS:
            continue
        key = _spec_key(raw_key)
        actual = specs.get(key, specs.get(raw_key))
        limit_num = _limit_float(limit)
        if limit_num is not None:
            got = _as_float(actual)
            if got is None:
                status = None if status is not False else False
                notes.append(f"{key} is not listed; check it is at most {limit_num:g} before buying")
            elif got <= limit_num + 1e-6:
                notes.append(f"{key} {got:g} fits the {limit_num:g} maximum")
            else:
                status = False
                notes.append(f"{key} {got:g} is over the {limit_num:g} maximum")
            continue
        wanted = str(limit).strip().lower()
        got_text = "" if actual is None else str(actual).strip().lower()
        if not got_text:
            status = None if status is not False else False
            notes.append(f"{key} is not listed; check it is {limit} before buying")
        elif wanted == got_text or wanted in got_text:
            notes.append(f"{key} matches {limit}")
        else:
            status = False
            notes.append(f"{key} is {actual}, needed {limit}")
    return status, "; ".join(notes) or "no size constraints on this query"


def assess_fit(specs: dict, constraints: dict) -> tuple[bool, str]:
    """Constraints are maximums for numbers and exact matches for text."""
    status, note = _fit(specs, constraints)
    return status is not False, note


def choose_for_query(query: ProductQuery, candidates: list[ProductQuote]) -> list[ProductQuote]:
    """Cheapest verified fit, plus one verified backup that also fits.

    Products whose page confirms the fit come before ones that don't list the attribute.
    """
    today = date.today().isoformat()
    fitting: list[tuple[bool, ProductQuote]] = []
    for quote in candidates:
        if not quote.url_verified:
            continue
        if query.max_price_usd is not None and quote.price_usd > query.max_price_usd:
            continue
        specs = dict(quote.specs or {})
        status, note = _fit(specs, query.constraints or {})
        if status is False:
            continue
        specs["quantity"] = query.quantity
        specs["query"] = query.query
        specs["price_as_of"] = specs.get("price_as_of") or today
        finding_id = quote.finding_id
        raw_finding = (query.constraints or {}).get("finding_id")
        if finding_id is None and isinstance(raw_finding, str):
            finding_id = raw_finding
        source = " Price from the store's search listing; confirm it at checkout." \
            if specs.get("verified_by") == "search_result" else ""
        fitting.append((
            status is None,
            quote.copy(
                update={
                    "specs": specs,
                    "fit_note": f"Prices as of {specs['price_as_of']}. {note}.{source}",
                    "finding_id": finding_id,
                }
            ),
        ))
    fitting.sort(key=lambda pair: (pair[0], pair[1].price_usd))
    ranked = [quote for _, quote in fitting]
    chosen: list[ProductQuote] = []
    if ranked:
        chosen.append(ranked[0].copy(update={"specs": {**ranked[0].specs, "role": "primary"}}))
    if len(ranked) > 1:
        chosen.append(ranked[1].copy(update={"specs": {**ranked[1].specs, "role": "backup"}}))
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


def _url_key(url: str) -> str:
    """host + path, so tracking parameters and a trailing slash don't hide a match."""
    parsed = urlparse(url.strip())
    return f"{_host(url)}{parsed.path.rstrip('/').lower()}"


def _candidate_from_raw(raw: dict) -> ProductQuote | None:
    url = str(raw.get("url") or "").strip()
    title = str(raw.get("title") or "").strip()
    price = _as_float(raw.get("price_usd"))
    if not title or not url.startswith(("http://", "https://")):
        return None
    merchant = str(raw.get("merchant") or "").strip() or _host(url)
    specs = dict(raw.get("specs")) if isinstance(raw.get("specs"), dict) else {}
    if price is None or price <= 0:
        price = 0.0
        specs["price_missing"] = True  # verify_quote reads the price from the product page
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


def _search_hits(response) -> dict[str, str]:
    """Every page the web search returned: url key -> page title. These URLs are real."""
    hits: dict[str, str] = {}
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", "") != "web_search_tool_result":
            continue
        results = getattr(block, "content", None)
        if not isinstance(results, list):
            continue  # an error object (e.g. max_uses_exceeded)
        for result in results:
            url = getattr(result, "url", None)
            if url:
                hits[_url_key(url)] = str(getattr(result, "title", "") or "")
    return hits


def _prompt(query: ProductQuery) -> str:
    keys = sorted({_spec_key(k) for k in (query.constraints or {}) if k not in _NOT_SPECS})
    spec_line = (
        f"In specs, report these attributes when the page states them, using exactly these keys: {', '.join(keys)}. "
        "Numbers in inches, pounds or counts as plain numbers.\n"
        if keys else ""
    )
    return (
        f"Find products currently for sale in the US for: {query.query}\n"
        f"Maximum price USD: {query.max_price_usd if query.max_price_usd is not None else 'none'}\n"
        f"Constraints (numbers are maximums the product must be within): {json.dumps(query.constraints or {})}\n"
        "Find the item the query names, not accessories or parts for it.\n"
        f"Search the web, then return ONLY a JSON array of up to {CANDIDATES} products, each from a different store "
        "when you can. Prefer stores that show the price on the product page (Walmart, Target, Wayfair, IKEA, "
        "Lowe's, Best Buy, the brand's own shop) as well as Amazon.\n"
        "Copy each url exactly from a search result you were given; never build or guess a URL. "
        "Use product pages, not search or category pages. If your first search only finds category or search "
        "pages, search once more for a specific brand and model.\n"
        "Each object has title (the product's name as the store lists it), url, merchant, price_usd as a number "
        "(null if the result doesn't show a price), image_url (or null), and specs (an object).\n"
        f"{spec_line}"
        "No markdown and no prose."
    )


def _request_kwargs(model: str, messages: list) -> dict:
    kwargs = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "messages": messages,
        "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
    }
    if re.match(r"claude-(opus|sonnet|haiku|fable)-5", model):
        # Finding and copying listings needs little reasoning; low effort keeps a query near 10 s.
        kwargs["output_config"] = {"effort": "low"}
    return kwargs


async def search_candidates(query: ProductQuery) -> tuple[list[ProductQuote], dict[str, str], dict]:
    """Candidates from one Claude web search, the search results it saw, and timing notes."""
    import anthropic

    model = _model()
    messages: list = [{"role": "user", "content": _prompt(query)}]
    t0 = time.perf_counter()
    async with anthropic.AsyncAnthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"], timeout=LLM_TIMEOUT_S, max_retries=0
    ) as client:
        response = await client.messages.create(**_request_kwargs(model, messages))
        hits = _search_hits(response)
        if response.stop_reason == "pause_turn":
            # The server-side search loop paused; send the turn back once to let it finish.
            messages.append({"role": "assistant", "content": response.content})
            response = await client.messages.create(**_request_kwargs(model, messages))
            hits.update(_search_hits(response))
    rows = _extract_json_array(_message_text(response))
    quotes = [quote for raw in rows[:CANDIDATES] if (quote := _candidate_from_raw(raw)) is not None]
    diag = {"model": model, "llm_s": round(time.perf_counter() - t0, 1), "stop": response.stop_reason,
            "candidates": len(quotes), "search_hits": len(hits)}
    return quotes, hits, diag


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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# Prices a product page states about itself, most reliable first: schema.org Product offers,
# Walmart's current price, microdata / Open Graph tags, then Amazon's price span. A bare
# "price" key isn't used: Shopify themes list variant prices in cents under that name.
_LD_JSON = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)
_PAGE_PRICE = [
    re.compile(r'"currentprice"\s*:\s*\{\s*"price"\s*:\s*(\d{1,6}(?:\.\d{1,2})?)'),
    re.compile(r'"priceamount"\s*:\s*(\d{1,6}(?:\.\d{1,2})?)'),  # Amazon's buy box
    re.compile(r'itemprop="price"[^>]*content="(\d{1,6}(?:\.\d{1,2})?)"'),
    re.compile(r'(?:product|og):price:amount"[^>]*content="(\d{1,6}(?:\.\d{1,2})?)"'),
    re.compile(r'class="a-offscreen">\$(\d{1,6}(?:\.\d{2})?)<'),
]


def _offer_price(node) -> float | None:
    """The first offer price of a schema.org Product anywhere in a JSON-LD tree."""
    if isinstance(node, list):
        for item in node:
            if (price := _offer_price(item)) is not None:
                return price
        return None
    if not isinstance(node, dict):
        return None
    if "product" in str(node.get("@type", "")).lower():
        offers = node.get("offers")
        for offer in offers if isinstance(offers, list) else [offers]:
            if isinstance(offer, dict):
                price = _as_float(offer.get("price") or offer.get("lowprice"))
                if price:
                    return price
    for value in node.values():
        if isinstance(value, (dict, list)) and (price := _offer_price(value)) is not None:
            return price
    return None


def _page_price(page: str) -> float | None:
    for block in _LD_JSON.findall(page):
        try:
            price = _offer_price(json.loads(block))
        except (json.JSONDecodeError, ValueError):
            continue
        if price:
            return price
    for pattern in _PAGE_PRICE:
        match = pattern.search(page)
        if match and float(match.group(1)) > 0:
            return float(match.group(1))
    return None


async def _fetch(client: httpx.AsyncClient, url: str, headers: dict | None) -> tuple[int | None, str]:
    """(status, lower-cased page text); status None when the request itself failed."""
    try:
        # httpx's timeout is per read; a slow multi-MB page also needs a deadline for the whole page.
        response = await asyncio.wait_for(client.get(url, headers=headers), PAGE_DEADLINE_S)
    except (httpx.HTTPError, UnicodeDecodeError, asyncio.TimeoutError):
        return None, ""
    # Big store pages (Amazon runs to 2-3 MB) state the price well past the first few hundred KB.
    return response.status_code, response.text[:PAGE_READ_CHARS].lower()


async def _page_text(client: httpx.AsyncClient, url: str, headers: dict | None) -> str:
    status, page = await _fetch(client, url, headers)
    return page if status is not None and status < 400 else ""


async def verify_quote(client: httpx.AsyncClient, quote: ProductQuote, hits: dict[str, str] | None = None) -> ProductQuote:
    """Verified when the store page shows the title or price.

    Stores that block bots (403/429/503, captcha pages) can't be read, so for those the URL must
    be one the web search itself returned, under a matching title: a real page, never a guessed URL.
    """
    status, page = await _fetch(client, quote.url, _BROWSER_HEADERS)
    loaded = status is not None and status < 400
    missing = bool(quote.specs.get("price_missing"))
    if loaded and missing:
        # No price from the search: only a product page that names the product and shows a price counts.
        price = _page_price(page)
        if price is not None and _title_matches(quote.title, page):
            specs = {k: v for k, v in quote.specs.items() if k != "price_missing"}
            return quote.copy(update={"price_usd": round(price, 2), "url_verified": True,
                                      "specs": {**specs, "verified_by": "page", "price_source": "page"}})
        return quote
    if missing:
        return quote  # a blocked page can't confirm a price we don't have
    if loaded and (_title_matches(quote.title, page) or _price_matches(quote.price_usd, page)):
        return quote.copy(update={"url_verified": True, "specs": {**quote.specs, "verified_by": "page"}})
    blocked = status is None or status in BLOCKED_STATUS or (loaded and any(w in page for w in BOT_WALL_WORDS))
    seen_title = (hits or {}).get(_url_key(quote.url))
    # Either title may be the longer one (stores truncate, Claude copies the full listing name).
    same = seen_title is not None and (_title_matches(quote.title, seen_title.lower())
                                       or _title_matches(seen_title, quote.title.lower()))
    if blocked and same:
        return quote.copy(update={"url_verified": True, "specs": {**quote.specs, "verified_by": "search_result"}})
    return quote


async def resolve_query(client: httpx.AsyncClient, query: ProductQuery) -> tuple[list[ProductQuote], str | None]:
    cache = _cache_load()
    cached = cache.get(query.query)
    if isinstance(cached, list) and cached:
        # Cached quotes still carry the finding, quantity and limits of the request that first
        # searched them: clear those and choose again for this query, so they link to this
        # request's finding and respect its price cap and size limits.
        loaded = [ProductQuote.model_validate(item).copy(update={"finding_id": None}) for item in cached]
        chosen = choose_for_query(query, loaded)
        if chosen:
            return chosen, None

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    t0 = time.perf_counter()
    raw_quotes, hits, diag = await search_candidates(query)
    checked = await asyncio.gather(*[verify_quote(client, quote, hits) for quote in raw_quotes])
    verified = [quote for quote in checked if quote.url_verified]
    chosen = choose_for_query(query, verified)
    log.info(
        "query=%r model=%s llm_s=%s stop=%s candidates=%s verified=%s (page %s, search %s) chosen=%s total_s=%.1f",
        query.query, diag["model"], diag["llm_s"], diag["stop"], diag["candidates"], len(verified),
        sum(1 for q in verified if q.specs.get("verified_by") == "page"),
        sum(1 for q in verified if q.specs.get("verified_by") == "search_result"),
        len(chosen), time.perf_counter() - t0,
    )
    if chosen:
        _cache_store(query.query, chosen)
        return chosen, None
    if not raw_quotes:
        return [], f"no products found for: {query.query}"
    return [], f"no verified products for: {query.query}"


async def find_products(request: FindProductsRequest) -> FindProductsResult:
    if chaos_tripped():
        raise ChaosFailure("CHAOS_PRODUCT_FINDER forced one failure")
    if request.queries and not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

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
        except Exception as exc:  # one failed search must not sink the other queries
            log.warning("query=%r failed: %s: %s", query.query, type(exc).__name__, exc)
            return [], f"search failed for: {query.query}"

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

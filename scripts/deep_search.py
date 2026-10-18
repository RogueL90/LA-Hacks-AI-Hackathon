"""Deep product search: fill the Product Finder's pools for everything the specialists ask for.

Builds every product search the four modes make on a home, across a range of profiles (aids,
child ages, makeover goals, rooms, styles, requirements), then runs each one wider than a live
request (up to 6 products from different stores, 3 web searches) and merges the verified products
into the cache pool. Live requests then choose from real options by their own price cap and size.

Run (live agents can keep running): .venv/bin/python -m scripts.deep_search [space_id] [--missing]
"""
import asyncio
import os
import sys
import time

os.environ.setdefault("PRODUCT_FINDER_CANDIDATES", "6")
os.environ.setdefault("PRODUCT_FINDER_SEARCHES", "3")
os.environ.setdefault("PRODUCT_FINDER_REFRESH", "1")

from shared import config  # noqa: E402,F401
from agents.actions.product_finder import search  # noqa: E402
from agents.specialists.baby.logic import analyze as baby  # noqa: E402
from agents.specialists.claim.logic import analyze as claim  # noqa: E402
from agents.specialists.elder.logic import analyze as elder  # noqa: E402
from agents.specialists.transformer.logic import analyze as transformer  # noqa: E402
from shared.demo_space import demo_space  # noqa: E402
from shared.models import FindProductsRequest, Profile  # noqa: E402
from shared.space_client import get_space  # noqa: E402


def profiles(space):
    rooms = [r.id for r in space.rooms]
    for aid in ("walker", "wheelchair", "cane"):
        for budget in (150, 300, 600):
            yield elder, Profile(mode="elder", mobility_aid=aid, night_trips=True, budget_usd=budget)
    for months in (9, 14, 24):
        yield baby, Profile(mode="baby", child_age_months=months, budget_usd=200)
    for goal in ("home office", "nursery", "home gym", "guest room"):
        for room in rooms[:8]:
            for req, style in (("", None), ("two monitors, keyboard and mouse", "Japandi"),
                               ("standing desk and a webcam for video calls", "modern")):
                yield transformer, Profile(mode="transform", goal=goal, room_id=room, requirements=req or None,
                                           style=style, budget_usd=800)
    yield claim, Profile(mode="claim", policy_type="replacement_cost")


async def main():
    ids = [a for a in sys.argv[1:] if not a.startswith("--")]
    space = await get_space(ids[0]) if ids else demo_space()
    queries = {}
    for analyze, profile in profiles(space):
        try:
            _, findings, _ = analyze(space, profile)
        except Exception as exc:  # a profile that doesn't fit this home
            print(f"skip {profile.mode}: {exc}")
            continue
        for f in findings:
            if f.product_query:
                queries.setdefault(f.product_query.query, f.product_query.copy(update={"max_price_usd": None}))
    if "--missing" in sys.argv:  # only searches whose pool is still empty
        pools = search._cache_load()
        queries = {q: pq for q, pq in queries.items() if not pools.get(q)}
    print(f"{len(queries)} distinct product searches for {space.space_id}", flush=True)
    before = {q: len(search._cache_load().get(q, [])) for q in queries}
    t0 = time.time()
    found = await search.find_products(FindProductsRequest(job_id="deep_search", queries=list(queries.values())))
    pools = search._cache_load()
    grown = sum(1 for q in queries if len(pools.get(q, [])) > before[q])
    sizes = [len(pools.get(q, [])) for q in queries]
    print(f"done in {time.time() - t0:.0f} s: {grown} pools grew; products per search: "
          f"min {min(sizes)}, median {sorted(sizes)[len(sizes) // 2]}, max {max(sizes)}; "
          f"{sum(1 for n in sizes if n == 0)} searches still empty")
    if found.error:
        print("notes:", found.error[:600])


if __name__ == "__main__":
    asyncio.run(main())

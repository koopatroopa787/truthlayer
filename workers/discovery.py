"""Public marketplace discovery — no auth required."""
import asyncio
import time
import httpx

_PUBLIC_BASE = "https://api.croo.network/backend/v1/public"
_cache: dict = {"agents": [], "services": [], "ts": 0.0}
_CACHE_TTL = 600  # 10 min


async def _refresh() -> None:
    async with httpx.AsyncClient(timeout=15) as c:
        agents, services = await asyncio.gather(
            c.get(f"{_PUBLIC_BASE}/agents?page_size=200"),
            _fetch_all_services(c),
        )
    _cache["agents"] = agents.json().get("agents", [])
    _cache["services"] = services
    _cache["ts"] = time.time()


async def _fetch_all_services(c: httpx.AsyncClient) -> list:
    out = []
    page = 1
    while True:
        r = await c.get(f"{_PUBLIC_BASE}/services?page={page}&page_size=20")
        data = r.json()
        items = data.get("items", [])
        out.extend(items)
        if len(out) >= int(data.get("total", 0)) or not items:
            break
        page += 1
    return out


async def get_marketplace() -> tuple[list, list]:
    """Return (agents, services), refreshing cache if stale."""
    if time.time() - _cache["ts"] > _CACHE_TTL:
        await _refresh()
    return _cache["agents"], _cache["services"]

"""Cross-Agent Arbitrage — find best-value agents for any task, expose savings."""
import asyncio
import json
import os
import re
from openai import OpenAI
from .discovery import get_marketplace

_openai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


async def _run_async(task: str, budget_usdc: float) -> str:
    agents, services = await get_marketplace()
    agent_map = {a["agentId"]: a for a in agents}

    candidates = []
    for svc in services:
        agent = agent_map.get(svc["agentId"], {})
        if agent.get("onlineStatus") != "online":
            continue
        price_usdc = int(svc.get("price", 0)) / 1_000_000
        if price_usdc > budget_usdc:
            continue
        candidates.append({
            "service_id": svc["serviceId"],
            "agent_name": agent.get("name", "?"),
            "service_name": svc["name"],
            "description": (agent.get("description") or svc.get("description") or "")[:200],
            "price_usdc": price_usdc,
            "completion_rate": agent.get("completionRate", 0),
            "avg_delivery": agent.get("avgDeliveryText", "—"),
            "orders_7d": int(svc.get("orders7d", 0)),
        })

    catalogue = json.dumps(candidates[:50], separators=(",", ":"))
    msg = _openai.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=900,
        messages=[{
            "role": "user",
            "content": (
                f"Task: {task}\nBudget: ${budget_usdc} USDC\n\n"
                f"Available agents:\n{catalogue}\n\n"
                "Find agents that can do this task. Group similar ones by function. "
                "Return ONLY valid JSON:\n"
                '{"best_value": {"service_id":"...","agent_name":"...","price_usdc":0.01,"reason":"..."}, '
                '"alternatives": [{"service_id":"...","agent_name":"...","price_usdc":0.0,"trade_off":"..."}], '
                '"most_proven": {"service_id":"...","agent_name":"...","orders_7d":0,"completion_rate":0}, '
                '"cheapest": {"service_id":"...","agent_name":"...","price_usdc":0.0}, '
                '"insight": "one sentence on pricing spread or gaps in the market"}'
            ),
        }],
    )
    raw = msg.choices[0].message.content
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    try:
        result = json.loads(m.group(1) if m else raw)
    except json.JSONDecodeError:
        result = {"insight": raw}

    result["task"] = task
    result["candidates_scanned"] = len(candidates)
    return json.dumps(result)


def run(requirements: str) -> str:
    try:
        req = json.loads(requirements)
        task = req.get("task", requirements)
        budget = float(req.get("budget_usdc", 100))
    except (json.JSONDecodeError, TypeError):
        task = requirements
        budget = 100
    return asyncio.run(_run_async(task, budget))

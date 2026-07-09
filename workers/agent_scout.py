"""Agent Scout — find the best CROO agents for any task.
No USDC needed: reads public marketplace data + GPT ranking.
"""
import asyncio
import json
import os
from openai import OpenAI
from .discovery import get_marketplace

_openai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def run(requirements: str) -> str:
    return asyncio.run(_run_async(requirements))


async def _run_async(requirements: str) -> str:
    try:
        req = json.loads(requirements)
        task = req.get("task", requirements)
        budget_usdc = float(req.get("budget_usdc", 999))
    except (json.JSONDecodeError, TypeError):
        task = requirements
        budget_usdc = 999

    agents, services = await get_marketplace()

    # build agent lookup: agentId → agent info
    agent_map = {a["agentId"]: a for a in agents}

    # filter online agents with budget, exclude ourselves
    candidates = []
    own_names = {"research_report", "fact_check"}
    for svc in services:
        agent = agent_map.get(svc["agentId"], {})
        if agent.get("onlineStatus") != "online":
            continue
        price_usdc = int(svc.get("price", 0)) / 1_000_000
        if price_usdc > budget_usdc:
            continue
        if agent.get("name", "").lower() in own_names:
            continue
        candidates.append({
            "service_id": svc["serviceId"],
            "agent_name": agent.get("name", "?"),
            "service_name": svc["name"],
            "description": (agent.get("description") or svc.get("description") or "")[:300],
            "price_usdc": price_usdc,
            "completion_rate": agent.get("completionRate", 0),
            "avg_delivery": agent.get("avgDeliveryText", "—"),
            "orders_7d": int(svc.get("orders7d", 0)),
        })

    # rank with GPT
    catalogue = json.dumps(candidates[:40], separators=(",", ":"))  # cap context
    msg = _openai.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=800,
        messages=[{
            "role": "user",
            "content": (
                f"Task: {task}\n\n"
                f"Available CROO agents (JSON):\n{catalogue}\n\n"
                "Pick the 5 best agents for this task. Return ONLY valid JSON:\n"
                '[{"rank": 1, "service_id": "...", "agent_name": "...", "service_name": "...", '
                '"price_usdc": 0.01, "reason": "one sentence why best fit", '
                '"completion_rate": 100, "avg_delivery": "< 1min"}]'
            )
        }]
    )

    raw = msg.choices[0].message.content
    # strip markdown fences
    import re
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    try:
        ranked = json.loads(m.group(1) if m else raw)
    except json.JSONDecodeError:
        ranked = []

    return json.dumps({
        "task": task,
        "recommendations": ranked,
        "total_candidates_scanned": len(candidates),
    })

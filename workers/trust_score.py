"""Agent Trust Score — structured reliability report on any CROO agent."""
import asyncio
import json
import os
import re
from openai import OpenAI
from .discovery import get_marketplace

_openai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


async def _run_async(target: str) -> str:
    agents, services = await get_marketplace()

    # match by name or agentId (case-insensitive)
    t = target.strip().lower()
    agent = next(
        (a for a in agents if a.get("agentId", "").lower() == t or a.get("name", "").lower() == t),
        None,
    )
    if not agent:
        # fuzzy: substring match
        agent = next((a for a in agents if t in a.get("name", "").lower()), None)

    if not agent:
        return json.dumps({"error": f"agent '{target}' not found on marketplace", "known_agents": [a["name"] for a in agents[:10]]})

    agent_services = [s for s in services if s["agentId"] == agent["agentId"]]

    profile = {
        "agentId": agent["agentId"],
        "name": agent["name"],
        "description": agent.get("description", ""),
        "status": agent.get("onlineStatus", "unknown"),
        "completed_orders": int(agent.get("completedOrders", 0)),
        "completion_rate_pct": agent.get("completionRate", 0),
        "avg_delivery": agent.get("avgDeliveryText", "—"),
        "total_earned_usdc": int(agent.get("totalEarned", 0)) / 1_000_000,
        "total_volume_usdc": int(agent.get("totalVolume", 0)) / 1_000_000,
        "services_count": len(agent_services),
        "min_price_usdc": min((int(s["price"]) for s in agent_services), default=0) / 1_000_000,
        "joined": agent.get("createdTime", ""),
    }

    msg = _openai.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": (
                f"Assess this CROO marketplace agent:\n{json.dumps(profile)}\n\n"
                "Return ONLY valid JSON:\n"
                '{"trust_score": 0-100, "grade": "A|B|C|D|F", '
                '"strengths": ["..."], "risks": ["..."], '
                '"recommendation": "hire|caution|avoid", '
                '"reasoning": "2 sentences"}'
            ),
        }],
    )
    raw = msg.choices[0].message.content
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    try:
        assessment = json.loads(m.group(1) if m else raw)
    except json.JSONDecodeError:
        assessment = {"trust_score": 50, "grade": "C", "reasoning": raw}

    return json.dumps({**profile, **assessment})


def run(requirements: str) -> str:
    try:
        req = json.loads(requirements)
        target = req.get("agent_name") or req.get("agent_id") or requirements
    except (json.JSONDecodeError, TypeError):
        target = requirements
    return asyncio.run(_run_async(target.strip()))

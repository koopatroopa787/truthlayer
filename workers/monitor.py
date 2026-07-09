"""Marketplace Monitor — watch for new agents matching criteria, deliver when found.
Deferred delivery: does NOT return immediately; polls until match or SLA expires.
"""
import asyncio
import json
import logging
import os
import time
from croo.agent_client import AgentClient
from croo.types import Config, DeliverOrderRequest, DeliverableType
from .discovery import get_marketplace, _refresh

log = logging.getLogger(__name__)

_POLL_INTERVAL = 600  # 10 min


def _matches(agent: dict, svc: dict, criteria: dict) -> bool:
    tags = set(agent.get("skillTagSlugs", []))
    wanted_tags = set(criteria.get("skill_tags", []))
    if wanted_tags and not wanted_tags.intersection(tags):
        return False
    if agent.get("completionRate", 0) < criteria.get("min_completion_rate", 0):
        return False
    price = int(svc.get("price", 0)) / 1_000_000
    if price > criteria.get("max_price_usdc", 9999):
        return False
    if criteria.get("online_only", True) and agent.get("onlineStatus") != "online":
        return False
    return True


async def run_async(requirements: str, order_id: str, client: AgentClient) -> None:
    """Long-running coroutine — delivers order_id when match found or SLA nears."""
    try:
        req = json.loads(requirements)
    except (json.JSONDecodeError, TypeError):
        req = {"criteria": {}, "monitor_hours": 24}

    criteria = req.get("criteria", {})
    monitor_seconds = float(req.get("monitor_hours", 24)) * 3600
    deadline = time.time() + monitor_seconds

    # snapshot agents we already know about (don't alert on existing ones)
    agents, services = await get_marketplace()
    known_ids = {a["agentId"] for a in agents}

    log.info("[monitor] order %s watching for %s, deadline in %.0fh", order_id, criteria, monitor_seconds / 3600)

    while time.time() < deadline - _POLL_INTERVAL:
        await asyncio.sleep(_POLL_INTERVAL)
        await _refresh()
        agents, services = await get_marketplace()
        agent_map = {a["agentId"]: a for a in agents}

        new_matches = []
        for svc in services:
            agent = agent_map.get(svc["agentId"], {})
            if agent.get("agentId") in known_ids:
                continue
            if _matches(agent, svc, criteria):
                new_matches.append({
                    "agent_name": agent.get("name"),
                    "agent_id": agent.get("agentId"),
                    "service_id": svc["serviceId"],
                    "service_name": svc["name"],
                    "price_usdc": int(svc.get("price", 0)) / 1_000_000,
                    "completion_rate": agent.get("completionRate", 0),
                    "description": (agent.get("description") or "")[:200],
                })

        known_ids = {a["agentId"] for a in agents}

        if new_matches:
            result = json.dumps({"status": "found", "new_agents": new_matches, "criteria": criteria})
            await client.deliver_order(order_id, DeliverOrderRequest(
                deliverable_type=DeliverableType.SCHEMA,
                deliverable_schema=result,
            ))
            log.info("[monitor] order %s delivered — %d new matches", order_id, len(new_matches))
            return

    # SLA approaching — deliver empty result
    result = json.dumps({"status": "no_new_agents", "criteria": criteria, "monitored_hours": req.get("monitor_hours", 24)})
    await client.deliver_order(order_id, DeliverOrderRequest(
        deliverable_type=DeliverableType.SCHEMA,
        deliverable_schema=result,
    ))
    log.info("[monitor] order %s timed out, no new matches", order_id)

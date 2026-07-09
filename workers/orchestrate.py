"""Orchestrated research: hire Argus (research) + Themis (verify) as sub-agents.
Requires USDC in the requester agent's wallet on Base (~$0.02/call total).
"""
import asyncio
import json
import os
import re
from openai import OpenAI
from croo.agent_client import AgentClient
from croo.types import Config, NegotiateOrderRequest

_openai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# Known service IDs (from public marketplace, stable)
ARGUS_SERVICE_ID = "45701b2d-547f-49a1-bf73-543fdb75af4c"   # Web Research $0.01
THEMIS_SERVICE_ID = "1f0be780-f777-4c71-8c94-b40cea2b1f7b"  # Fact-Check $0.01

_cfg = Config(
    base_url=os.environ["CROO_API_URL"],
    ws_url=os.environ["CROO_WS_URL"],
)


async def _hire_and_await(client: AgentClient, service_id: str, requirements: str, timeout: int = 300) -> str:
    """Negotiate → pay → poll for delivery. Returns deliverable text/schema."""
    neg = await client.negotiate_order(NegotiateOrderRequest(
        service_id=service_id,
        requirements=requirements,
    ))

    # wait for provider to accept (order_created)
    deadline = asyncio.get_event_loop().time() + 60
    order = None
    while asyncio.get_event_loop().time() < deadline:
        negs = await client.list_negotiations()
        for n in negs:
            if n.negotiation_id == neg.negotiation_id and n.status == "accepted":
                orders = await client.list_orders()
                for o in orders:
                    if o.negotiation_id == neg.negotiation_id:
                        order = o
                        break
                break
        if order:
            break
        await asyncio.sleep(3)

    if not order:
        raise TimeoutError(f"provider did not accept negotiation {neg.negotiation_id}")

    await client.pay_order(order.order_id)

    # poll for delivery
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        o = await client.get_order(order.order_id)
        if o.status == "completed":
            delivery = await client.get_delivery(order.order_id)
            return delivery.deliverable_text or delivery.deliverable_schema or ""
        if o.status in ("rejected", "expired"):
            raise RuntimeError(f"sub-order {order.order_id} ended with status {o.status}")
        await asyncio.sleep(5)

    raise TimeoutError(f"sub-order {order.order_id} timed out")


async def _run_async(query: str) -> str:
    # Use research_report agent as requester
    client = AgentClient(_cfg, os.environ["SERVICE_RESEARCH_ID"])

    try:
        # Step 1: hire Argus for web research
        argus_result = await _hire_and_await(client, ARGUS_SERVICE_ID, query)

        # Step 2: hire Themis to verify key claims from Argus output
        themis_result = await _hire_and_await(client, THEMIS_SERVICE_ID, argus_result[:1000])
    finally:
        await client.close()

    # Step 3: synthesize with GPT
    msg = _openai.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": (
                f"Research query: {query}\n\n"
                f"Raw research (from Argus agent):\n{argus_result}\n\n"
                f"Verification result (from Themis agent):\n{themis_result}\n\n"
                "Synthesize into a final verified report. Return ONLY valid JSON:\n"
                '{"title": "...", "summary": "...", "key_findings": [...], '
                '"trust_score": 0.0-1.0, "verified_claims": [...], '
                '"uncertain_claims": [...], "sources": [...]}'
            )
        }]
    )
    raw = msg.choices[0].message.content
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    try:
        report = json.loads(m.group(1) if m else raw)
    except json.JSONDecodeError:
        report = {"title": query, "summary": raw, "trust_score": 0.5}

    report["_meta"] = {"sub_agents": ["Argus (web research)", "Themis (fact-check)"], "a2a": True}
    return json.dumps(report)


def run(requirements: str) -> str:
    try:
        req = json.loads(requirements)
        query = req.get("query", requirements)
    except (json.JSONDecodeError, TypeError):
        query = requirements
    return asyncio.run(_run_async(query))

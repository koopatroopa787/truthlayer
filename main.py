"""TruthLayer — 5 CROO agents: research, verify, monitor, trust, arbitrage."""
import asyncio
import logging
import os

from dotenv import load_dotenv
load_dotenv() or load_dotenv(".env.example")

from croo.agent_client import AgentClient
from croo.types import Config, DeliverOrderRequest, DeliverableType, EventType

import workers.research as research_worker
import workers.verify as verify_worker
import workers.agent_scout as scout_worker
import workers.orchestrate as orchestrate_worker
import workers.trust_score as trust_worker
import workers.arbitrage as arbitrage_worker
import workers.monitor as monitor_worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_cfg = Config(
    base_url=os.environ["CROO_API_URL"],
    ws_url=os.environ["CROO_WS_URL"],
)


def _make_provider(sdk_key: str, dispatch: dict, fallback_worker, name: str):
    """
    dispatch: service_uuid → worker module (optional, used when agent has multiple services)
    Workers with run_async(requirements, order_id, client) handle deferred delivery (monitor).
    Workers with run(requirements) → immediate delivery.
    """
    client = AgentClient(_cfg, sdk_key)
    pending: dict[str, tuple[str, str]] = {}  # order_id → (service_id, requirements)

    def _on_negotiation(event) -> None:
        asyncio.create_task(_accept(event.negotiation_id))

    def _on_order_created(event) -> None:
        asyncio.create_task(_store(event.order_id, event.negotiation_id))

    def _on_order_paid(event) -> None:
        asyncio.create_task(_deliver(event.order_id))

    async def _accept(negotiation_id: str) -> None:
        try:
            neg = await client.get_negotiation(negotiation_id)
            log.info("[%s] negotiation %s svc=%s", name, negotiation_id, neg.service_id)
            await client.accept_negotiation(negotiation_id)
        except Exception as e:
            log.error("[%s] accept error: %s", name, e)

    async def _store(order_id: str, negotiation_id: str) -> None:
        try:
            neg = await client.get_negotiation(negotiation_id)
            pending[order_id] = (neg.service_id, neg.requirements)
            log.info("[%s] order %s stored", name, order_id)
        except Exception as e:
            log.error("[%s] store error: %s", name, e)

    async def _deliver(order_id: str) -> None:
        entry = pending.pop(order_id, None)
        if not entry:
            log.warning("[%s] order_paid unknown order %s", name, order_id)
            return
        service_id, requirements = entry
        worker = dispatch.get(service_id, fallback_worker)
        log.info("[%s] order %s → %s", name, order_id, getattr(worker, "__name__", "?"))
        try:
            if hasattr(worker, "run_async"):
                # deferred: worker delivers itself (used by monitor)
                await worker.run_async(requirements, order_id, client)
            else:
                result = await asyncio.to_thread(worker.run, requirements)
                await client.deliver_order(order_id, DeliverOrderRequest(
                    deliverable_type=DeliverableType.SCHEMA,
                    deliverable_schema=result,
                ))
                log.info("[%s] delivered order %s", name, order_id)
        except Exception as e:
            log.error("[%s] error order %s: %s", name, order_id, e)
            try:
                await client.reject_order(order_id, f"internal error: {e}")
            except Exception:
                pass

    async def run() -> None:
        stream = await client.connect_websocket()
        stream.on(EventType.NEGOTIATION_CREATED, _on_negotiation)
        stream.on(EventType.ORDER_CREATED, _on_order_created)
        stream.on(EventType.ORDER_PAID, _on_order_paid)
        log.info("[%s] WebSocket connected", name)
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await stream.close()
            await client.close()

    return run


def _svc(key: str) -> str:
    return os.environ.get(key, "")


async def main() -> None:
    providers = [
        # research agent: research + scout + orchestrate (dispatch by service UUID)
        _make_provider(
            sdk_key=os.environ["SERVICE_RESEARCH_ID"],
            dispatch={k: v for k, v in {
                _svc("RESEARCH_SVC_ID"): research_worker,
                _svc("SCOUT_SVC_ID"): scout_worker,
                _svc("ORCHESTRATE_SVC_ID"): orchestrate_worker,
            }.items() if k},
            fallback_worker=research_worker,
            name="research",
        ),
        # verify agent
        _make_provider(
            sdk_key=os.environ["SERVICE_VERIFY_ID"],
            dispatch={k: v for k, v in {_svc("VERIFY_SVC_ID"): verify_worker}.items() if k},
            fallback_worker=verify_worker,
            name="verify",
        ),
        # monitor agent
        _make_provider(
            sdk_key=os.environ["MONITOR_SVC_ID"],
            dispatch={},
            fallback_worker=monitor_worker,
            name="monitor",
        ),
        # trust score agent
        _make_provider(
            sdk_key=os.environ["TRUST_SVC_ID"],
            dispatch={},
            fallback_worker=trust_worker,
            name="trust",
        ),
        # arbitrage agent
        _make_provider(
            sdk_key=os.environ["ARBITRAGE_SVC_ID"],
            dispatch={},
            fallback_worker=arbitrage_worker,
            name="arbitrage",
        ),
    ]
    log.info("TruthLayer starting 5 providers...")
    await asyncio.gather(*[p() for p in providers])


if __name__ == "__main__":
    asyncio.run(main())

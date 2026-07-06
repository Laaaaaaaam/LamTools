import logging
import time
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.billing_service import calc_cost, record_billing

logger = logging.getLogger(__name__)


@dataclass
class LLMCallRecord:
    node: str
    model_id: str
    provider_id: str
    session_id: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    cost: float = 0.0
    billing_type: str = "agent"
    system_prompt: str = ""
    user_content: str = ""
    response_text: str = ""
    extra: dict = field(default_factory=dict)


def extract_tokens(response: dict) -> tuple[int, int]:
    usage = response.get("usage", {})
    if isinstance(usage, dict):
        return usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    return 0, 0


async def log_and_bill(
    db: AsyncSession,
    record: LLMCallRecord,
) -> None:
    logger.info(
        f"LLM call: node={record.node} model={record.model_id} "
        f"tokens_in={record.tokens_in} tokens_out={record.tokens_out} "
        f"cost={record.cost:.4f} latency={record.latency_ms}ms"
    )
    if record.system_prompt:
        logger.info(f"[{record.node}] system_prompt: {record.system_prompt}")
    if record.user_content:
        logger.info(f"[{record.node}] user_content: {record.user_content}")
    if record.response_text:
        logger.info(f"[{record.node}] response: {record.response_text}")

    if not db or not record.provider_id:
        return

    try:
        from sqlalchemy import select
        from app.models.api_provider import ApiProvider

        result = await db.execute(select(ApiProvider).where(ApiProvider.id == record.provider_id))
        provider = result.scalar_one_or_none()
        if not provider:
            return

        if record.cost == 0.0:
            record.cost = calc_cost(provider, tokens_in=record.tokens_in, tokens_out=record.tokens_out)

        detail = {
            "type": record.billing_type,
            "node": record.node,
            "model_id": record.model_id,
            "tokens_in": record.tokens_in,
            "tokens_out": record.tokens_out,
            "latency_ms": record.latency_ms,
        }
        if record.extra:
            detail.update(record.extra)

        await record_billing(
            db,
            session_id=record.session_id,
            provider_id=provider.id,
            billing_type=provider.billing_type.value,
            tokens_in=record.tokens_in,
            tokens_out=record.tokens_out,
            cost=record.cost,
            currency=provider.currency,
            detail=detail,
        )
    except Exception as e:
        logger.warning(f"log_and_bill failed for node={record.node}: {e}")


class LLMTimer:
    def __init__(self):
        self._start = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args):
        pass

    @property
    def ms(self) -> int:
        return int((time.perf_counter() - self._start) * 1000)

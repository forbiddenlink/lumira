"""Unified AI spend guard: kill switch + daily budget for image and LLM calls.

Every metered AI call (image generation *and* LLM/Anthropic) should pass through
this module so that:

- a single env kill switch (``LUMIRA_AI_KILL_SWITCH``) can halt all AI work
  without a redeploy, and
- a single dollar-denominated daily cap (``LUMIRA_DAILY_SPEND_USD_MAX``) bounds
  total spend across image + LLM, backed by Redis so the counter survives a
  process restart and is shared across worker processes.

If Redis is unavailable the ledger degrades to a per-process in-memory counter
(better than nothing; logged so the degradation is visible). Previously the
image caps were per-process globals that reset on restart and the LLM spend was
entirely uncapped and unlogged.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class SpendKillSwitchError(RuntimeError):
    """Raised when the global AI kill switch is engaged."""


class SpendBudgetExceededError(RuntimeError):
    """Raised when the daily dollar budget would be exceeded."""


# --- Rough cost model (USD) -------------------------------------------------
# Deliberately conservative estimates; override per-provider as pricing shifts.
# The point is a spend *ceiling*, not accounting-grade billing.
_LLM_COST_PER_MTOK = {
    # (input_per_million, output_per_million)
    "default": (3.0, 15.0),  # Claude Sonnet-class
}


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def kill_switch_engaged() -> bool:
    """True when LUMIRA_AI_KILL_SWITCH is set to a truthy value."""
    return _truthy(os.getenv("LUMIRA_AI_KILL_SWITCH"))


def assert_ai_enabled(context: str = "ai") -> None:
    """Raise SpendKillSwitchError if the global AI kill switch is engaged."""
    if kill_switch_engaged():
        logger.error("ai_kill_switch_engaged", context=context)
        raise SpendKillSwitchError(
            "AI generation is disabled (LUMIRA_AI_KILL_SWITCH is set)."
        )


def estimate_llm_cost_usd(
    input_tokens: int, output_tokens: int, model: str = "default"
) -> float:
    rates = _LLM_COST_PER_MTOK.get(model) or _LLM_COST_PER_MTOK["default"]
    in_rate, out_rate = rates
    return (input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate


class _InMemoryLedger:
    """Fallback daily ledger when Redis is not available."""

    def __init__(self) -> None:
        self._day: str | None = None
        self._spent = 0.0

    def _roll(self, today: str) -> None:
        if today != self._day:
            self._day, self._spent = today, 0.0

    def get(self, today: str) -> float:
        self._roll(today)
        return self._spent

    def add(self, today: str, amount: float) -> float:
        self._roll(today)
        self._spent += amount
        return self._spent


_memory_ledger = _InMemoryLedger()
_redis_client = None
_redis_checked = False


def _get_redis() -> Any:
    """Return a redis client if REDIS_URL is set and reachable, else None."""
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    _redis_checked = True
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        import redis  # noqa: PLC0415

        client = redis.Redis.from_url(url, socket_connect_timeout=2)
        client.ping()
        _redis_client = client
    except Exception as e:  # pragma: no cover - depends on runtime infra
        logger.warning("spend_guard_redis_unavailable", error=str(e))
        _redis_client = None
    return _redis_client


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _daily_cap_usd() -> float:
    """Daily dollar cap; 0 (default) disables the dollar ceiling."""
    try:
        return float(os.getenv("LUMIRA_DAILY_SPEND_USD_MAX", "0"))
    except ValueError:
        return 0.0


def current_spend_usd() -> float:
    today = _today()
    client = _get_redis()
    if client is None:
        return _memory_ledger.get(today)
    try:
        raw = client.get(f"lumira:spend:{today}")
        return float(raw) if raw else 0.0
    except Exception as e:  # pragma: no cover
        logger.warning("spend_guard_redis_read_failed", error=str(e))
        return _memory_ledger.get(today)


def check_budget(pending_usd: float, context: str = "ai") -> None:
    """Raise SpendBudgetExceededError if this spend would breach the daily cap.

    Also enforces the kill switch, so a single call guards both.
    """
    assert_ai_enabled(context)
    cap = _daily_cap_usd()
    if cap <= 0:
        return
    spent = current_spend_usd()
    if spent + pending_usd > cap:
        logger.error(
            "spend_budget_exceeded",
            context=context,
            spent_usd=round(spent, 4),
            pending_usd=round(pending_usd, 4),
            daily_cap_usd=cap,
        )
        raise SpendBudgetExceededError(
            f"Daily AI spend cap reached (${spent:.2f}/${cap:.2f}). "
            "Raise LUMIRA_DAILY_SPEND_USD_MAX or wait for the daily reset."
        )


def record_spend(amount_usd: float, context: str = "ai") -> float:
    """Add to today's ledger (Redis if available) and return the new total."""
    if amount_usd <= 0:
        return current_spend_usd()
    today = _today()
    client = _get_redis()
    if client is None:
        return _memory_ledger.add(today, amount_usd)
    try:
        # Store as integer micro-dollars for atomic INCRBY, then expire in 48h.
        micros = int(round(amount_usd * 1_000_000))
        key = f"lumira:spend:micros:{today}"
        new_micros = client.incrby(key, micros)
        client.expire(key, 172800)
        new_total = float(new_micros) / 1_000_000
        # Mirror a dollar view for reads.
        client.set(f"lumira:spend:{today}", f"{new_total:.6f}", ex=172800)
        return new_total
    except Exception as e:  # pragma: no cover
        logger.warning("spend_guard_redis_write_failed", error=str(e))
        return _memory_ledger.add(today, amount_usd)


def record_llm_usage(
    input_tokens: int, output_tokens: int, model: str = "default"
) -> float:
    """Log an LLM call's token usage and add its estimated cost to the ledger."""
    cost = estimate_llm_cost_usd(input_tokens, output_tokens, model)
    total = record_spend(cost, context="llm")
    logger.info(
        "llm_usage",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        est_cost_usd=round(cost, 5),
        day_total_usd=round(total, 4),
    )
    return cost


def check_and_record_images(
    provider: str, num_images: int, cap: int, cost_per_image_usd: float = 0.0
) -> None:
    """Enforce a per-UTC-day image cap for a metered provider, Redis-backed so
    the counter survives a restart and is shared across worker processes.

    Also enforces the kill switch and the shared dollar budget. ``cap<=0``
    disables the image-count ceiling (dollar budget may still apply).
    """
    assert_ai_enabled(provider)
    if cost_per_image_usd > 0:
        check_budget(cost_per_image_usd * num_images, context=provider)

    if cap > 0:
        today = _today()
        client = _get_redis()
        key = f"lumira:images:{provider}:{today}"
        used = 0
        if client is not None:
            try:
                raw = client.get(key)
                used = int(raw) if raw else 0
            except Exception as e:  # pragma: no cover
                logger.warning("spend_guard_image_read_failed", error=str(e))
        else:
            used = int(_memory_ledger.get(f"img:{provider}:{today}"))

        if used + num_images > cap:
            logger.error(
                "image_budget_exceeded",
                provider=provider,
                used=used,
                requested=num_images,
                daily_cap=cap,
            )
            raise SpendBudgetExceededError(
                f"{provider} daily image budget exceeded ({used}/{cap}). "
                "Raise the cap or wait for the daily reset."
            )

        if client is not None:
            try:
                client.incrby(key, num_images)
                client.expire(key, 172800)
            except Exception as e:  # pragma: no cover
                logger.warning("spend_guard_image_write_failed", error=str(e))
                _memory_ledger.add(f"img:{provider}:{today}", num_images)
        else:
            _memory_ledger.add(f"img:{provider}:{today}", num_images)

    if cost_per_image_usd > 0:
        record_spend(cost_per_image_usd * num_images, context=provider)


def guarded_messages_create(client: Any, **kwargs: Any) -> Any:
    """Wrap Anthropic ``client.messages.create`` with kill switch, budget check,
    and usage logging. Drop-in for ``client.messages.create(**kwargs)``.
    """
    model = kwargs.get("model", "default")
    # Pre-call: kill switch + budget check using max_tokens as an output ceiling.
    max_tokens = int(kwargs.get("max_tokens", 1024))
    pre_estimate = estimate_llm_cost_usd(max_tokens, max_tokens, model)
    check_budget(pre_estimate, context="llm")

    response = client.messages.create(**kwargs)

    # Post-call: record actual usage when the SDK exposes it.
    usage = getattr(response, "usage", None)
    if usage is not None:
        record_llm_usage(
            getattr(usage, "input_tokens", 0),
            getattr(usage, "output_tokens", 0),
            model=str(model),
        )
    return response

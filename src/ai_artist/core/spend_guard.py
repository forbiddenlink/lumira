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
import threading
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
        self._balances: dict[str, float] = {}

    def _roll(self, today: str) -> None:
        if today != self._day:
            self._day = today
            self._balances.clear()

    def get(self, today: str, key: str = "spend") -> float:
        self._roll(today)
        return self._balances.get(key, 0.0)

    def add(self, today: str, amount: float, key: str = "spend") -> float:
        self._roll(today)
        self._balances[key] = self._balances.get(key, 0.0) + amount
        return self._balances[key]


_memory_ledger = _InMemoryLedger()
_memory_ledger_lock = threading.Lock()
_redis_client = None
_redis_checked = False
_redis_init_lock = threading.Lock()

_RESERVE_IMAGE_BUDGET = """
local image_key = KEYS[1]
local spend_key = KEYS[2]
local image_count = tonumber(ARGV[1])
local image_cap = tonumber(ARGV[2])
local spend_micros = tonumber(ARGV[3])
local spend_cap_micros = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])

local used_images = tonumber(redis.call('GET', image_key) or '0')
if image_cap > 0 and used_images + image_count > image_cap then
    return {-1, used_images, tonumber(redis.call('GET', spend_key) or '0')}
end

local used_spend = tonumber(redis.call('GET', spend_key) or '0')
if spend_cap_micros > 0 and used_spend + spend_micros > spend_cap_micros then
    return {-2, used_images, used_spend}
end

local new_images = used_images
if image_count > 0 then
    new_images = redis.call('INCRBY', image_key, image_count)
    redis.call('EXPIRE', image_key, ttl)
end
local new_spend = used_spend
if spend_micros > 0 then
    new_spend = redis.call('INCRBY', spend_key, spend_micros)
    redis.call('EXPIRE', spend_key, ttl)
end
return {0, new_images, new_spend}
"""


def _get_redis() -> Any:
    """Return a redis client if REDIS_URL is set and reachable, else None."""
    global _redis_client, _redis_checked
    with _redis_init_lock:
        if _redis_checked:
            return _redis_client
        url = os.getenv("REDIS_URL")
        if url:
            try:
                import redis  # noqa: PLC0415

                client = redis.Redis.from_url(url, socket_connect_timeout=2)
                client.ping()
                _redis_client = client
            except Exception as e:  # pragma: no cover - depends on runtime infra
                logger.warning("spend_guard_redis_unavailable", error=str(e))
                _redis_client = None
        _redis_checked = True
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
        with _memory_ledger_lock:
            return _memory_ledger.get(today)
    try:
        raw = client.get(f"lumira:spend:micros:{today}")
        return int(raw) / 1_000_000 if raw else 0.0
    except Exception as e:  # pragma: no cover
        logger.warning("spend_guard_redis_read_failed", error=str(e))
        with _memory_ledger_lock:
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
        with _memory_ledger_lock:
            return _memory_ledger.add(today, amount_usd)
    try:
        # Store as integer micro-dollars for atomic INCRBY, then expire in 48h.
        micros = int(round(amount_usd * 1_000_000))
        key = f"lumira:spend:micros:{today}"
        new_micros = client.incrby(key, micros)
        client.expire(key, 172800)
        new_total = float(new_micros) / 1_000_000
        return new_total
    except Exception as e:  # pragma: no cover
        logger.warning("spend_guard_redis_write_failed", error=str(e))
        with _memory_ledger_lock:
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
    _reserve_budget(provider, num_images, cap, cost_per_image_usd * num_images)


def _reserve_budget(
    provider: str,
    num_images: int,
    cap: int,
    amount_usd: float,
) -> tuple[str, Any]:
    """Reserve image counts and/or estimated spend, returning day and backend."""
    assert_ai_enabled(provider)
    today = _today()
    image_key = f"lumira:images:{provider}:{today}"
    spend_key = f"lumira:spend:micros:{today}"
    spend_micros = int(round(amount_usd * 1_000_000))
    spend_cap_micros = int(round(_daily_cap_usd() * 1_000_000))
    client = _get_redis()

    if client is not None:
        try:
            result = client.eval(
                _RESERVE_IMAGE_BUDGET,
                2,
                image_key,
                spend_key,
                num_images,
                cap,
                spend_micros,
                spend_cap_micros,
                172800,
            )
            status, used_images, used_spend = (int(value) for value in result)
            if status == -1:
                raise SpendBudgetExceededError(
                    f"{provider} daily image budget exceeded ({used_images}/{cap}). "
                    "Raise the cap or wait for the daily reset."
                )
            if status == -2:
                raise SpendBudgetExceededError(
                    f"Daily AI spend cap reached (${used_spend / 1_000_000:.2f}/"
                    f"${_daily_cap_usd():.2f}). Raise the cap or wait for reset."
                )
            return today, client
        except SpendBudgetExceededError:
            raise
        except Exception as e:  # pragma: no cover
            logger.warning("spend_guard_atomic_reservation_failed", error=str(e))
            if provider == "llm":
                # An uncertain shared reservation must not authorize another call.
                raise SpendBudgetExceededError(
                    "Unable to reserve the shared LLM budget. Retry when Redis is available."
                ) from e

    # The fallback is process-local, but remains atomic within this process.
    with _memory_ledger_lock:
        used_images = int(_memory_ledger.get(today, key=f"img:{provider}"))
        fallback_spend = _memory_ledger.get(today)
        if cap > 0 and used_images + num_images > cap:
            raise SpendBudgetExceededError(
                f"{provider} daily image budget exceeded ({used_images}/{cap}). "
                "Raise the cap or wait for the daily reset."
            )
        if spend_cap_micros > 0 and fallback_spend + (spend_micros / 1_000_000) > (
            spend_cap_micros / 1_000_000
        ):
            raise SpendBudgetExceededError(
                f"Daily AI spend cap reached (${fallback_spend:.2f}/${_daily_cap_usd():.2f}). "
                "Raise the cap or wait for the daily reset."
            )
        _memory_ledger.add(today, num_images, key=f"img:{provider}")
        if spend_micros > 0:
            _memory_ledger.add(today, spend_micros / 1_000_000)
    return today, None


def _settle_llm_reservation(
    reservation: tuple[str, Any], reserved_usd: float, actual_usd: float
) -> None:
    """Adjust the original day's reservation; retain it if accounting fails."""
    today, client = reservation
    delta_micros = int(round(actual_usd * 1_000_000)) - int(
        round(reserved_usd * 1_000_000)
    )
    if client is None:
        with _memory_ledger_lock:
            # A call completing after midnight must not roll the ledger backwards.
            if _memory_ledger._day == today:
                _memory_ledger.add(today, delta_micros / 1_000_000)
        return
    try:
        # Do not recreate an expired reservation as a negative balance.
        client.eval(
            "if redis.call('EXISTS', KEYS[1]) == 1 then "
            "return redis.call('INCRBY', KEYS[1], ARGV[1]) end return 0",
            1,
            f"lumira:spend:micros:{today}",
            delta_micros,
        )
    except Exception as e:
        logger.warning("spend_guard_llm_settlement_failed", error=str(e))


def guarded_messages_create(client: Any, **kwargs: Any) -> Any:
    """Wrap Anthropic ``client.messages.create`` with kill switch, budget check,
    and usage logging. Drop-in for ``client.messages.create(**kwargs)``.
    """
    model = kwargs.get("model", "default")
    # Pre-call: kill switch + budget check using max_tokens as an output ceiling.
    max_tokens = int(kwargs.get("max_tokens", 1024))
    pre_estimate = estimate_llm_cost_usd(max_tokens, max_tokens, model)
    reservation = _reserve_budget("llm", 0, 0, pre_estimate)

    response = client.messages.create(**kwargs)

    # Unknown usage (including failed calls) retains the estimate conservatively.
    usage = getattr(response, "usage", None)
    if usage is not None:
        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)
        if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
            return response
        cost = estimate_llm_cost_usd(input_tokens, output_tokens, model=str(model))
        _settle_llm_reservation(reservation, pre_estimate, cost)
        logger.info(
            "llm_usage",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            est_cost_usd=round(cost, 5),
            day_total_usd=round(current_spend_usd(), 4),
        )
    return response

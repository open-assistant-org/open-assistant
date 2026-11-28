"""Per-call LLM usage recorder for accurate metered billing.

Captures the provider's authoritative ``response.usage`` for every LLM call and
persists it to the ``llm_consumption`` ledger. The managed platform polls
``/managed/usage``, which sums this ledger by month — replacing the old
``SUM(messages.token_count)`` estimate that only counted visible message text
and missed all input/context tokens and auxiliary calls.

Design notes
------------
* **Singleton, wired at startup.** ``LLMClient`` is constructed ad-hoc across
  many services with no DB handle, so the recorder is a process-level singleton
  set once in ``main.lifespan`` via :meth:`UsageRecorder.set_db`. When unset
  (tests / standalone scripts) recording is a silent no-op.
* **Boundary capture.** The OpenAI/Groq SDK's ``chat.completions.create`` is
  wrapped once in ``LLMClient.__init__``; every call site funnels through it, so
  usage is recorded without touching any caller.
* **Never raises.** Billing must never break chat — all DB work is wrapped in
  try/except and logged. Delegates to :class:`LlmConsumptionRepository`, which
  uses :class:`BaseRepository` connection handling.
* **Provider scope.** Works for any OpenAI-compatible provider that returns
  ``usage`` on non-streaming completions (OpenRouter, OpenAI, Anthropic, Groq;
  Ollama/vLLM usually). When ``usage`` is absent the recorder stores zeros and
  flags ``missing_usage`` so the gap is visible rather than silent.
"""

from typing import Any, Dict, Optional

from src.core.database import DatabaseManager
from src.core.repositories.llm_consumption import LlmConsumptionRepository
from src.utils.logger import get_logger
from src.utils.token_counter import count_tokens

logger = get_logger(__name__)


def _attr(obj: Any, name: str) -> Any:
    """Read an attribute from a possibly-None SDK object, returning None if absent."""
    if obj is None:
        return None
    return getattr(obj, name, None)


def _extract_usage(usage: Any) -> Dict[str, int]:
    """Extract token fields from a provider ``usage`` object.

    Handles OpenAI / OpenRouter / Groq shapes, including the optional
    ``prompt_tokens_details.cached_tokens`` and
    ``completion_tokens_details.reasoning_tokens`` breakdowns. Returns a dict
    with prompt/completion/total/cached/reasoning integers (0 when absent).
    """
    prompt = int(_attr(usage, "prompt_tokens") or 0)
    completion = int(_attr(usage, "completion_tokens") or 0)
    total = _attr(usage, "total_tokens")
    total = int(total) if total is not None else prompt + completion

    prompt_details = _attr(usage, "prompt_tokens_details")
    completion_details = _attr(usage, "completion_tokens_details")
    cached = int(_attr(prompt_details, "cached_tokens") or 0)
    reasoning = int(_attr(completion_details, "reasoning_tokens") or 0)

    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "cached_tokens": cached,
        "reasoning_tokens": reasoning,
    }


def _estimate_prompt_tokens(messages: Optional[list], model: str) -> int:
    """Estimate the input size of an OpenAI-format ``messages`` payload.

    Local tiktoken count (cl100k_base) — used only when the provider cannot
    report usage, so the row is a flagged approximation rather than a silent 0.
    Never raises; tolerant of dict/SimpleNamespace/mixed message shapes.
    """
    if not messages:
        return 0
    total = 0
    for m in messages:
        try:
            content = m.get("content") if isinstance(m, dict) else getattr(m, "content", None)
            if isinstance(content, str):
                total += count_tokens(content, model)
            elif isinstance(content, list):
                for part in content:
                    text = (
                        part.get("text") if isinstance(part, dict) else getattr(part, "text", None)
                    )
                    if isinstance(text, str):
                        total += count_tokens(text, model)
        except Exception:  # noqa: BLE001 - estimation must never raise
            continue
    return total


class UsageRecorder:
    """Records per-call LLM usage into the ``llm_consumption`` ledger.

    Process-level singleton — one instance shared app-wide, configured with the
    ``DatabaseManager`` at startup. Writes go through
    :class:`LlmConsumptionRepository` (and thus :class:`BaseRepository`).
    """

    _db: Optional[DatabaseManager] = None

    @classmethod
    def set_db(cls, db_manager: DatabaseManager) -> None:
        """Wire the database manager. Called once at app startup."""
        cls._db = db_manager
        logger.info("UsageRecorder wired to database")

    @classmethod
    def clear(cls) -> None:
        """Detach the database manager. Used in tests to reset state."""
        cls._db = None

    @classmethod
    def record(
        cls,
        usage: Any,
        *,
        provider: str,
        model: str,
        conversation_id: Optional[str] = None,
        messages: Optional[list] = None,
    ) -> None:
        """Persist one ``llm_consumption`` row for a single LLM call.

        Never raises — failures are logged so a billing glitch cannot break chat.
        No-op when no database is wired (tests / standalone). When ``usage`` is
        None but ``messages`` are supplied, the prompt side is estimated locally
        (``count_tokens``) and flagged ``estimated`` so a provider that cannot
        report streamed usage still leaves a visible input-cost row.
        """
        if cls._db is None:
            return

        try:
            fields = _extract_usage(usage)
            metadata: Dict[str, Any] = {}
            if usage is None:
                metadata["missing_usage"] = True
                if messages:
                    fields["prompt_tokens"] = _estimate_prompt_tokens(messages, model)
                    fields["total_tokens"] = fields["prompt_tokens"]
                    metadata["estimated"] = True
            else:
                openrouter_cost = _attr(usage, "cost")
                if openrouter_cost is not None:
                    metadata["openrouter_cost"] = openrouter_cost

            LlmConsumptionRepository(cls._db).record(
                provider=provider,
                model=model,
                prompt_tokens=fields["prompt_tokens"],
                completion_tokens=fields["completion_tokens"],
                total_tokens=fields["total_tokens"],
                cached_tokens=fields["cached_tokens"],
                reasoning_tokens=fields["reasoning_tokens"],
                conversation_id=conversation_id,
                metadata=metadata or None,
            )
        except Exception as e:  # noqa: BLE001 - billing must not break chat
            logger.error(f"UsageRecorder failed to record usage: {e}")

    @classmethod
    def record_failure(
        cls,
        *,
        provider: str,
        model: str,
        messages: Optional[list] = None,
        conversation_id: Optional[str] = None,
    ) -> None:
        """Persist a marker row for an LLM call that failed before returning.

        A request that times out or gets a 4xx/5xx never reaches ``record`` —
        without this marker its (possibly partially billed) usage would be
        silently absent from the ledger. The row carries zero billed tokens and
        ``metadata.failed`` (excluded from billing totals; visible for
        reconciliation). Never raises; no-op when no database is wired.
        """
        if cls._db is None:
            return

        try:
            estimated = _estimate_prompt_tokens(messages, model) if messages else 0
            LlmConsumptionRepository(cls._db).record(
                provider=provider,
                model=model,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                conversation_id=conversation_id,
                metadata={"failed": True, "estimated_prompt_tokens": estimated},
            )
        except Exception as e:  # noqa: BLE001 - billing must not break chat
            logger.error(f"UsageRecorder failed to record failure marker: {e}")


# Module-level singleton used by LLMClient.
usage_recorder = UsageRecorder

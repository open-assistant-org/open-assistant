"""Repository for the per-call LLM consumption ledger.

Backs accurate metered billing: ``/managed/usage`` sums this table by month
instead of the legacy ``SUM(messages.token_count)`` estimate.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.core.repositories.base import BaseRepository


class LlmConsumptionRepository(BaseRepository):
    """Repository for the ``llm_consumption`` table."""

    def record(
        self,
        *,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        cached_tokens: int = 0,
        reasoning_tokens: int = 0,
        conversation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Insert one consumption row (a single LLM call's usage).

        Never raises on success; callers wrap failures as needed.
        """
        self.insert(
            "llm_consumption",
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "provider": provider,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cached_tokens": cached_tokens,
                "reasoning_tokens": reasoning_tokens,
                "conversation_id": conversation_id,
                "metadata": json.dumps(metadata) if metadata else None,
            },
        )

    def get_monthly_totals(self, months: int = 12) -> List[Dict[str, Any]]:
        """Return token totals grouped by calendar month for the trailing N months.

        Mirrors the shape of the legacy ``MessageRepository.get_monthly_token_totals``
        but reads real provider usage from the ledger. The deploy-time baseline
        row is current-month-dated so it is included in the trailing window and
        bridges the platform's lifetime watermark.

        Args:
            months: Trailing number of months to include.

        Returns:
            List of dicts with keys: year, month, tokens_input, tokens_output,
            tokens_total (ascending by year, month). The current month is always
            present even when usage is zero.
        """
        query = """
            SELECT
                CAST(strftime('%Y', timestamp) AS INTEGER) AS year,
                CAST(strftime('%m', timestamp) AS INTEGER) AS month,
                COALESCE(SUM(prompt_tokens), 0) AS tokens_input,
                COALESCE(SUM(completion_tokens), 0) AS tokens_output,
                COALESCE(SUM(total_tokens), 0) AS tokens_total
            FROM llm_consumption
            WHERE timestamp >= datetime('now', ? || ' months')
            GROUP BY year, month
            ORDER BY year ASC, month ASC
        """
        offset = f"-{months}"
        return self.fetch_all(query, (offset,))

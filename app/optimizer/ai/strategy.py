from __future__ import annotations

from datetime import datetime
from typing import Sequence

from optimizer.models import Attempt, HistoricalAttempt, Word
from optimizer.strategy import Strategy
from optimizer.ai.run import VocabularyRun
from optimizer.ai.selector import VocabularySelector


class AiStrategy(Strategy):
    """
    The ai-strategy: a recency-weighted cross-run understanding model.

    Composes ``VocabularyRun`` (run mechanics) and ``VocabularySelector``
    (understanding / priority) and exposes them through the ``Strategy``
    API, overriding its hooks.
    """

    def __init__(
        self,
        history: Sequence[HistoricalAttempt] = (),
        *,
        seed: int | None = None,
        **selector_kwargs,
    ):
        super().__init__(seed=seed)
        self._selector = VocabularySelector(history, seed=seed,
                                            **selector_kwargs)

    @property
    def selector(self) -> VocabularySelector:
        """The underlying selector (understanding / priority model)."""

        return self._selector

    def create_run(
        self,
        words: Sequence[Word],
        attempts: Sequence[Attempt] = (),
        **kwargs,
    ) -> VocabularyRun:
        return VocabularyRun(words, attempts, **kwargs)

    def compose_run(
        self,
        words: Sequence[Word],
        n: int | None = None,
        *,
        now: datetime | None = None,
    ) -> list[Word]:
        """The words the AI strategy puts in a run: everything that needs
        practice (weakest first, capped by ``n``) plus a small periodic
        sample of the words known for sure (validation)."""
        return self._selector.compose_run(words, n=n, now=now)

    def understanding(
        self,
        word_id: int | str,
        *,
        now: datetime | None = None,
    ) -> float:
        return self._selector.understanding(word_id, now=now)

    def selection_priority(
        self,
        word: Word,
        *,
        now: datetime | None = None,
    ) -> float:
        return self._selector.selection_priority(word, now=now)
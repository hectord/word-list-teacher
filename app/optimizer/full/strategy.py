from __future__ import annotations

from datetime import datetime
from typing import Sequence

from optimizer.models import Attempt, HistoricalAttempt, Word
from optimizer.strategy import Strategy
from optimizer.full.run import FullRun
from optimizer.full.selector import FullSelector


class FullStrategy(Strategy):
    """
    The full-strategy: the run mechanics used by the application, plus the
    selection signals it derives from its history (error probability and
    mastery through completed runs).

    Composes ``FullRun`` (port of ``app/learn.py`` ``Session``) and
    ``FullSelector`` and exposes them through the ``Strategy`` API,
    overriding its hooks.
    """

    def __init__(
        self,
        history: Sequence[HistoricalAttempt] = (),
        *,
        seed: int | None = None,
        **selector_kwargs,
    ):
        super().__init__(seed=seed)
        self._selector = FullSelector(history, seed=seed, **selector_kwargs)

    @property
    def selector(self) -> FullSelector:
        """The underlying selector (error / mastery model)."""

        return self._selector

    def create_run(
        self,
        words: Sequence[Word],
        attempts: Sequence[Attempt] = (),
        **kwargs,
    ) -> FullRun:
        return FullRun(words, attempts, **kwargs)

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
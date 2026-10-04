from __future__ import annotations

from datetime import datetime
import random
from typing import Iterable, Sequence

from optimizer.models import HistoricalAttempt, Word


class FullSelector:
    """
    The "full" selection strategy — ranking / selection built on the
    signals the application derives from its attempt history:

    - ``error_probability(word_id)``: failures / (failures + successes),
      the same error rate the vocabulary page displays;
    - ``mastered(word_id)``: the word was answered correctly at least once
      in the supplied history. To mirror the application's rule ("a
      completed run makes the word known"), supply the attempts of
      completed runs only.

    ``understanding`` is then ``1 - error_probability`` for mastered words
    and ``0`` (by default) for words never mastered, so fresh words get the
    highest selection priority.

    The select / rank methods have the same signatures as the ai-strategy
    (``optimizer.ai.VocabularySelector``) so the two strategies are
    interchangeable. ``now`` parameters are accepted for API symmetry but
    not used: the full strategy has no recency model.
    """

    def __init__(
        self,
        history: Sequence[HistoricalAttempt] = (),
        *,
        unseen_understanding: float = 0.0,
        audit_floor: float = 0.05,
        level_weights: dict[str, float] | None = None,
        seed: int | None = None,
    ):
        if not 0.0 <= unseen_understanding <= 1.0:
            raise ValueError("unseen_understanding must be between 0 and 1")
        if not 0.0 <= audit_floor <= 1.0:
            raise ValueError("audit_floor must be between 0 and 1")

        self.history = list(history)
        self.unseen_understanding = unseen_understanding
        self.audit_floor = audit_floor

        self.level_weights = level_weights or {
            "B1": 1.20,
            "B2": 1.00,
            "C1": 0.70,
        }

        self._rng = random.Random(seed)

    # ------------------------------------------------------------- data
    def _outcomes(self, word_id: int | str) -> tuple[int, int]:
        successes = 0
        failures = 0

        for attempt in self.history:
            if attempt.word_id == word_id:
                if attempt.success:
                    successes += 1
                else:
                    failures += 1

        return successes, failures

    def mastered(self, word_id: int | str) -> bool:
        """Answered correctly at least once in the supplied history."""
        successes, _ = self._outcomes(word_id)
        return successes > 0

    def error_probability(self, word_id: int | str) -> float:
        """Failures / (failures + successes); 0.0 with no attempts."""
        successes, failures = self._outcomes(word_id)
        total = successes + failures

        if not total:
            return 0.0

        return failures / total

    # ------------------------------------------------------ understanding
    def understanding(
        self,
        word_id: int | str,
        *,
        now: datetime | None = None,
    ) -> float:
        """
        Estimate of how well the learner knows the word, in [0, 1].

        Never-mastered words return ``unseen_understanding`` (0 by
        default); mastered words return ``1 - error_probability``.
        """
        if not self.mastered(word_id):
            return self.unseen_understanding

        return 1.0 - self.error_probability(word_id)

    def understanding_map(
        self,
        words: Iterable[Word],
        *,
        now: datetime | None = None,
    ) -> dict[int | str, float]:
        return {
            word.id: self.understanding(word.id, now=now)
            for word in words
        }

    def rank_understanding(
        self,
        words: Iterable[Word],
        *,
        now: datetime | None = None,
        strongest_first: bool = True,
    ) -> list[tuple[Word, float]]:
        ranked = [
            (word, self.understanding(word.id, now=now))
            for word in words
        ]

        return sorted(
            ranked,
            key=lambda item: item[1],
            reverse=strongest_first,
        )

    def _weakness(self, word: Word) -> float:
        return 1.0 - self.understanding(word.id)

    def selection_priority(
        self,
        word: Word,
        *,
        now: datetime | None = None,
    ) -> float:
        """
        Priority for including the word in a future run.

        Weak (badly known or never mastered) words receive high priority.
        A small audit floor keeps strong words from becoming permanently
        invisible, exactly like the ai-strategy.
        """
        level_weight = self.level_weights.get(word.level, 1.0)
        importance = max(word.importance, 0.0)

        return (
            self.audit_floor + self._weakness(word)
        ) * level_weight * importance

    def rank_for_next_run(
        self,
        words: Iterable[Word],
        *,
        now: datetime | None = None,
    ) -> list[tuple[Word, float]]:
        ranked = [
            (word, self.selection_priority(word, now=now))
            for word in words
        ]

        return sorted(
            ranked,
            key=lambda item: item[1],
            reverse=True,
        )

    def select_words(
        self,
        words: Sequence[Word],
        n: int | None = None,
        *,
        now: datetime | None = None,
        weighted_random: bool = False,
    ) -> list[Word]:
        """
        Select words for a new run.

        By default, returns the highest-priority words deterministically.
        With ``weighted_random=True`` selection is still biased toward
        high-priority words but contains randomness.
        """
        words = list(words)

        if n is None:
            n = len(words)

        if n < 0:
            raise ValueError("n must be >= 0")

        n = min(n, len(words))

        if not weighted_random:
            return [
                word
                for word, _ in self.rank_for_next_run(words, now=now)[:n]
            ]

        remaining = list(words)
        selected: list[Word] = []

        while remaining and len(selected) < n:
            weights = [
                max(self.selection_priority(word, now=now), 1e-9)
                for word in remaining
            ]

            chosen = self._rng.choices(
                remaining,
                weights=weights,
                k=1,
            )[0]

            selected.append(chosen)
            remaining.remove(chosen)

        return selected
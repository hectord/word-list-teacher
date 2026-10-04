from __future__ import annotations

from datetime import datetime
import random
from typing import Iterable, Sequence

from optimizer.models import Attempt, Word


class Strategy:
    """
    Base class for word-selection strategies.

    A strategy knows how to:

    - ``create_run``: build a run over a set of words (plus the attempts
      which already happened);
    - ``understanding``: estimate how well a word is known, in [0, 1];
    - ``selection_priority``: score how valuable it is to test a word now.

    The ranking and selection methods (``rank_understanding``,
    ``rank_for_next_run``, ``select_words``, ``understanding_map``) are
    implemented here on top of those three hooks, so concrete strategies in
    the sub-packages only have to override the hooks.

    ``create_run`` cannot be generic: the strategy subclass has to
    implement it. The default ``understanding`` / ``selection_priority``
    are kept deliberately simple so a bare ``Strategy`` is instantiable
    and usable (every word is equally unknown, priority is the raw
    usefulness: level weight x importance).

    Strategies are interchangeable: ``optimizer.ai.AiStrategy`` and
    ``optimizer.full.FullStrategy`` both subclass this class and expose the
    same API.
    """

    DEFAULT_LEVEL_WEIGHTS = {"B1": 1.20, "B2": 1.00, "C1": 0.70}
    AUDIT_FLOOR = 0.05

    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)

    # ------------------------------------------------------------- hooks
    def create_run(
        self,
        words: Sequence[Word],
        attempts: Sequence[Attempt] = (),
        **kwargs,
    ):
        """Build a run over ``words`` and the given ``attempts``.

        The returned object manages one run (``next_word`` / ``answer`` /
        ``remaining_words`` / ``finished`` ...) and is reconstructible from
        ``words`` + ``attempts``.
        """
        raise NotImplementedError(
            "create_run() must be implemented by the strategy subclass"
        )

    def understanding(
        self,
        word_id: int | str,
        *,
        now: datetime | None = None,
    ) -> float:
        """Estimated understanding of ``word_id``, in [0, 1].

        Default: no history, so every word is considered unknown (0.0).
        """
        return 0.0

    def selection_priority(
        self,
        word: Word,
        *,
        now: datetime | None = None,
    ) -> float:
        """How valuable it is to test this word in the next run.

        Default: raw usefulness of an unknown word (little audit floor on
        top) scaled by level weight and importance.
        """
        understanding = self.understanding(word.id, now=now)
        weakness = 1.0 - understanding

        level_weight = self.DEFAULT_LEVEL_WEIGHTS.get(word.level, 1.0)
        importance = max(word.importance, 0.0)

        return (
            self.AUDIT_FLOOR + weakness
        ) * level_weight * importance

    # -------------------------------------------------------- ranking
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

    # ------------------------------------------------------- selection
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

        By default returns the highest-priority words deterministically;
        with ``weighted_random=True`` selection is biased toward
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
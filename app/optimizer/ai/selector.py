from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from math import exp, log
import random
from typing import Iterable, Sequence

from optimizer.models import HistoricalAttempt, Word


class VocabularySelector:
    """
    Cross-run learning model.

    Responsibilities:
        1. Estimate understanding(word_id) in [0, 1].
        2. Rank words by understanding.
        3. Rank/select words for a future run.

    The selector does not persist anything. Supply historical attempts when
    constructing it.
    """

    def __init__(
        self,
        history: Sequence[HistoricalAttempt] = (),
        *,
        recency_half_life_days: float = 60.0,
        failure_penalty: float = 0.45,
        confidence_rate: float = 0.80,
        unseen_understanding: float = 0.0,
        level_weights: dict[str, float] | None = None,
        audit_floor: float = 0.05,
        seed: int | None = None,
    ):
        if recency_half_life_days <= 0:
            raise ValueError("recency_half_life_days must be > 0")
        if failure_penalty < 0:
            raise ValueError("failure_penalty must be >= 0")
        if confidence_rate <= 0:
            raise ValueError("confidence_rate must be > 0")
        if not 0.0 <= unseen_understanding <= 1.0:
            raise ValueError("unseen_understanding must be between 0 and 1")
        if not 0.0 <= audit_floor <= 1.0:
            raise ValueError("audit_floor must be between 0 and 1")

        self.history = list(history)
        self.recency_half_life_days = recency_half_life_days
        self.failure_penalty = failure_penalty
        self.confidence_rate = confidence_rate
        self.unseen_understanding = unseen_understanding
        self.audit_floor = audit_floor

        self.level_weights = level_weights or {
            "B1": 1.20,
            "B2": 1.00,
            "C1": 0.70,
        }

        self._rng = random.Random(seed)

    @staticmethod
    def _normalized_time(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def attempts_for_word(
        self,
        word_id: int | str,
    ) -> list[HistoricalAttempt]:
        return sorted(
            [
                attempt
                for attempt in self.history
                if attempt.word_id == word_id
            ],
            key=lambda attempt: self._normalized_time(attempt.tested_at),
        )

    def runs_for_word(
        self,
        word_id: int | str,
    ) -> dict[int | str, list[HistoricalAttempt]]:
        runs: dict[int | str, list[HistoricalAttempt]] = defaultdict(list)

        for attempt in self.attempts_for_word(word_id):
            runs[attempt.run_id].append(attempt)

        return dict(runs)

    def run_score(
        self,
        attempts: Sequence[HistoricalAttempt],
    ) -> float:
        """
        Convert one run into a score in [0, 1].

        Examples with failure_penalty=0.45:
            S         -> 1.00
            F S       -> ~0.64
            F F S     -> ~0.41
            F F F S   -> ~0.26

        An incomplete run with no success scores 0.
        """
        failures = 0

        for attempt in attempts:
            if attempt.success:
                return exp(-self.failure_penalty * failures)
            failures += 1

        return 0.0

    def first_try_history(
        self,
        word_id: int | str,
    ) -> list[bool]:
        """
        One boolean per run:
            True  = first attempt in that run was a success
            False = first attempt was a failure
        """
        runs = self.runs_for_word(word_id)
        ordered = sorted(
            runs.values(),
            key=lambda attempts: self._normalized_time(attempts[0].tested_at),
        )
        return [attempts[0].success for attempts in ordered if attempts]

    def understanding(
        self,
        word_id: int | str,
        *,
        now: datetime | None = None,
    ) -> float:
        """
        Estimate current understanding in [0, 1].

        Interpretation:
            approximately how strongly the evidence suggests that the learner
            can recall the word correctly on first presentation now.

        Notes:
            - first-attempt success in a run is strongest evidence
            - failures before eventual success reduce that run's score
            - recent runs matter more than old ones
            - repeated runs increase confidence
        """
        if now is None:
            now = datetime.now(timezone.utc)
        now = self._normalized_time(now)

        runs = self.runs_for_word(word_id)

        if not runs:
            return self.unseen_understanding

        decay = log(2.0) / self.recency_half_life_days

        weighted_score = 0.0
        total_weight = 0.0

        for attempts in runs.values():
            if not attempts:
                continue

            score = self.run_score(attempts)

            last_attempt = max(
                self._normalized_time(attempt.tested_at)
                for attempt in attempts
            )

            age_days = max(
                0.0,
                (now - last_attempt).total_seconds() / 86400.0,
            )

            weight = exp(-decay * age_days)

            weighted_score += weight * score
            total_weight += weight

        if total_weight == 0:
            return self.unseen_understanding

        raw_score = weighted_score / total_weight

        # One perfect run is useful evidence, but not equivalent to several
        # independent perfect runs. Low evidence is softly pulled toward 0.5.
        n_runs = len(runs)
        confidence = 1.0 - exp(-self.confidence_rate * n_runs)

        score = (
            confidence * raw_score
            + (1.0 - confidence) * 0.5
        )

        return max(0.0, min(1.0, score))

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

    def selection_priority(
        self,
        word: Word,
        *,
        now: datetime | None = None,
    ) -> float:
        """
        Priority for including a word in a future run.

        Understanding and priority are intentionally separate:
            understanding -> how well the learner knows the word
            priority      -> how valuable it is to test the word now

        Weak words receive high priority. A small audit floor keeps strong
        words from becoming permanently invisible.
        """
        understanding = self.understanding(word.id, now=now)
        weakness = 1.0 - understanding

        level_weight = self.level_weights.get(word.level, 1.0)
        importance = max(word.importance, 0.0)

        return (
            self.audit_floor + weakness
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

        If weighted_random=True, selection is still biased toward high-priority
        words but contains randomness.
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

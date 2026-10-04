from __future__ import annotations

from datetime import datetime, timezone
import random
from typing import Sequence

from optimizer.models import Attempt, RunStatus, Word, WordRunStats


class VocabularyRun:
    """
    Represents one learning run.

    A word remains active until it receives one success in this run.

    The run is fully reconstructible from:
        - the words that belong to the run
        - the attempts that already happened

    No persistence is performed by this class.
    """

    def __init__(
        self,
        words: Sequence[Word],
        attempts: Sequence[Attempt] = (),
        *,
        cooldown: int = 3,
        seed: int | None = None,
        level_weights: dict[str, float] | None = None,
    ):
        if cooldown < 0:
            raise ValueError("cooldown must be >= 0")

        self._words = {word.id: word for word in words}
        self._word_ids = [word.id for word in words]

        if len(self._words) != len(self._word_ids):
            raise ValueError("Word IDs must be unique inside a run.")

        self._attempts = list(attempts)
        self.cooldown = cooldown
        self._rng = random.Random(seed)

        self.level_weights = level_weights or {
            "B1": 1.20,
            "B2": 1.00,
            "C1": 0.70,
        }

        self._validate_attempts()

    def _validate_attempts(self) -> None:
        valid_ids = set(self._word_ids)

        for attempt in self._attempts:
            if attempt.word_id not in valid_ids:
                raise ValueError(
                    f"Attempt references word {attempt.word_id!r}, "
                    "which is not part of this run."
                )

        # Once a word succeeds, no later attempt for that same word should exist
        # in a valid run history.
        completed: set[int | str] = set()
        for attempt in self._attempts:
            if attempt.word_id in completed:
                raise ValueError(
                    f"Attempt found after word {attempt.word_id!r} "
                    "had already succeeded in this run."
                )
            if attempt.success:
                completed.add(attempt.word_id)

    @property
    def attempts(self) -> tuple[Attempt, ...]:
        return tuple(self._attempts)

    @property
    def words(self) -> tuple[Word, ...]:
        return tuple(self._words[word_id] for word_id in self._word_ids)

    @property
    def total_words(self) -> int:
        return len(self._word_ids)

    @property
    def completed_word_ids(self) -> set[int | str]:
        return {
            attempt.word_id
            for attempt in self._attempts
            if attempt.success
        }

    @property
    def completed_words(self) -> tuple[Word, ...]:
        completed = self.completed_word_ids
        return tuple(
            self._words[word_id]
            for word_id in self._word_ids
            if word_id in completed
        )

    @property
    def remaining_word_ids(self) -> list[int | str]:
        completed = self.completed_word_ids
        return [
            word_id
            for word_id in self._word_ids
            if word_id not in completed
        ]

    @property
    def remaining_words(self) -> tuple[Word, ...]:
        return tuple(self._words[word_id] for word_id in self.remaining_word_ids)

    @property
    def recent_word_ids(self) -> list[int | str]:
        return [attempt.word_id for attempt in self._attempts]

    @property
    def finished(self) -> bool:
        return len(self.remaining_word_ids) == 0

    def stats(self, word_id: int | str) -> WordRunStats:
        if word_id not in self._words:
            raise KeyError(f"Unknown word ID: {word_id!r}")

        attempts = [
            attempt
            for attempt in self._attempts
            if attempt.word_id == word_id
        ]

        successes = sum(1 for attempt in attempts if attempt.success)
        failures = sum(1 for attempt in attempts if not attempt.success)

        return WordRunStats(
            word_id=word_id,
            attempts=len(attempts),
            successes=successes,
            failures=failures,
            completed=successes > 0,
        )

    def status(self) -> RunStatus:
        successes = sum(1 for attempt in self._attempts if attempt.success)
        failures = sum(1 for attempt in self._attempts if not attempt.success)

        return RunStatus(
            total_words=self.total_words,
            completed_words=len(self.completed_word_ids),
            remaining_words=len(self.remaining_word_ids),
            attempts=len(self._attempts),
            successes=successes,
            failures=failures,
            finished=self.finished,
        )

    def failures(self, word_id: int | str) -> int:
        return self.stats(word_id).failures

    def priority(self, word_id: int | str) -> float:
        """
        Within-run priority.

        Historical cross-run difficulty belongs in VocabularySelector.
        Within a run, words that have already failed are more likely to
        reappear once cooldown allows them.
        """
        word = self._words[word_id]
        failure_count = self.failures(word_id)

        level_weight = self.level_weights.get(word.level, 1.0)
        difficulty = 1.0 + 0.60 * failure_count

        return max(
            1e-9,
            difficulty * level_weight * max(word.importance, 0.0),
        )

    def next_word(self) -> Word | None:
        """
        Select the next word using weighted randomness.

        Recently attempted words are temporarily excluded if other candidates
        are available. If every remaining word is inside the cooldown window,
        the cooldown is automatically relaxed.

        Calling next_word() does not mutate the run. Only answer() does.
        """
        candidates = self.remaining_word_ids

        if not candidates:
            return None

        if self.cooldown:
            recent = set(self.recent_word_ids[-self.cooldown:])
            spaced = [
                word_id
                for word_id in candidates
                if word_id not in recent
            ]
            if spaced:
                candidates = spaced

        weights = [self.priority(word_id) for word_id in candidates]

        selected_id = self._rng.choices(
            candidates,
            weights=weights,
            k=1,
        )[0]

        return self._words[selected_id]

    def answer(
        self,
        word_id: int | str,
        success: bool,
        tested_at: datetime | None = None,
    ) -> Attempt:
        """
        Record one attempt and return it.

        Your application can persist the returned Attempt wherever it wants.
        """
        if word_id not in self._words:
            raise ValueError(f"Word {word_id!r} is not part of this run.")

        if word_id in self.completed_word_ids:
            raise ValueError(
                f"Word {word_id!r} has already succeeded in this run."
            )

        if tested_at is None:
            tested_at = datetime.now(timezone.utc)

        attempt = Attempt(
            word_id=word_id,
            success=bool(success),
            tested_at=tested_at,
        )

        self._attempts.append(attempt)
        return attempt

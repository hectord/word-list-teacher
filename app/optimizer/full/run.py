from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import random
from typing import Sequence

from optimizer.models import Attempt, RunStatus, Word, WordRunStats


class FullRun:
    """
    The "full" run strategy — the run mechanics used by the application
    (a port of ``app/learn.py`` ``Session``).

    Behaviour
    ---------
    - every word of the run is asked until it succeeds once;
    - the next word is chosen at random among the remaining words,
      temporarily skipping the most recently attempted words
      (``cooldown``, default 4, like ``Session.SKIP_LAST_WORDS_COUNT``);
    - failures are counted per word.

    Like ``VocabularyRun``, it is fully reconstructible from the words of
    the run plus the attempts which already happened, and it performs no
    persistence.

    Correctness of an answer is decided by the caller: ``answer()`` takes
    the ``success`` boolean (same API as the ai-strategy) instead of the
    raw typed text, which belongs to the application.
    """

    COOLDOWN = 4

    def __init__(
        self,
        words: Sequence[Word],
        attempts: Sequence[Attempt] = (),
        *,
        cooldown: int | None = None,
        seed: int | None = None,
    ):
        if cooldown is not None and cooldown < 0:
            raise ValueError("cooldown must be >= 0")

        self._words = {word.id: word for word in words}
        self._word_ids = [word.id for word in words]

        if len(self._words) != len(self._word_ids):
            raise ValueError("Word IDs must be unique inside a run.")

        self.cooldown = self.COOLDOWN if cooldown is None else cooldown
        self._rng = random.Random(seed)
        self._attempts = list(attempts)
        self._error_count_by_word: dict[int | str, int] = defaultdict(int)
        self._remaining: set[int | str] = set(self._word_ids)

        self._validate_attempts()

    def _validate_attempts(self) -> None:
        preceded_by_success: set[int | str] = set()

        for attempt in self._attempts:
            if attempt.word_id not in self._words:
                raise ValueError(
                    f"Attempt references word {attempt.word_id!r}, "
                    "which is not part of this run."
                )

            if attempt.word_id in preceded_by_success:
                raise ValueError(
                    f"Attempt found after word {attempt.word_id!r} "
                    "had already succeeded in this run."
                )

            if attempt.success:
                preceded_by_success.add(attempt.word_id)
                self._remaining.discard(attempt.word_id)
            else:
                self._error_count_by_word[attempt.word_id] += 1

    # ------------------------------------------------------------- state
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
        return [
            word_id
            for word_id in self._word_ids
            if word_id not in self.completed_word_ids
        ]

    @property
    def remaining_words(self) -> tuple[Word, ...]:
        return tuple(
            self._words[word_id]
            for word_id in self.remaining_word_ids
        )

    @property
    def recent_word_ids(self) -> list[int | str]:
        """The attempted words, most recent last (used by the cooldown)."""
        return [attempt.word_id for attempt in self._attempts]

    @property
    def finished(self) -> bool:
        return not self.remaining_word_ids

    # ---------------------------------------------------------- per word
    def stats(self, word_id: int | str) -> WordRunStats:
        if word_id not in self._words:
            raise KeyError(f"Unknown word ID: {word_id!r}")

        attempts = [
            attempt
            for attempt in self._attempts
            if attempt.word_id == word_id
        ]

        successes = sum(1 for attempt in attempts if attempt.success)
        failures = len(attempts) - successes

        return WordRunStats(
            word_id=word_id,
            attempts=len(attempts),
            successes=successes,
            failures=failures,
            completed=successes > 0,
        )

    def failures(self, word_id: int | str) -> int:
        return self.stats(word_id).failures

    def error_counts(self) -> dict[int | str, int]:
        return dict(self._error_count_by_word)

    def words_in_error(self) -> list[tuple[Word, int]]:
        """Words with at least one failure, weakest (most failures) first
        — the counterpart of ``Session.vocabulary_left``."""
        ranked = [
            (self._words[word_id], count)
            for word_id, count in self._error_count_by_word.items()
        ]
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked

    def new_words_learned(self) -> int:
        """Words with no failure in this run (``Session.new_words_learned``)."""
        return self.total_words - len(self._error_count_by_word)

    def accuracy(self) -> float:
        """Port of ``Session.accuracy`` (0..100): the share of tested
        words with no error."""
        tested = self.total_words - len(
            self._remaining - set(self._error_count_by_word)
        )

        if not tested:
            return 100.0

        word_in_error = len(self._error_count_by_word)
        return 100.0 - word_in_error / tested * 100.0

    def status(self) -> RunStatus:
        successes = sum(1 for attempt in self._attempts if attempt.success)
        failures = len(self._attempts) - successes

        return RunStatus(
            total_words=self.total_words,
            completed_words=len(self.completed_word_ids),
            remaining_words=len(self.remaining_word_ids),
            attempts=len(self._attempts),
            successes=successes,
            failures=failures,
            finished=self.finished,
        )

    # ------------------------------------------------------------- flow
    def next_word(self) -> Word | None:
        """
        Select the next word to ask.

        Mirrors ``Session._pick_next_word``: random choice among the
        remaining words, skipping the last ``cooldown`` attempted words
        (unless that would leave nothing, in which case the skip is
        relaxed). Does not mutate the run; only ``answer()`` does.
        """
        candidates = self.remaining_word_ids

        if not candidates:
            return None

        possible = list(candidates)
        recent = self.recent_word_ids[-self.cooldown:]

        for word_id in reversed(recent):
            if len(possible) == 1:
                break
            if word_id in possible:
                possible.remove(word_id)

        return self._words[self._rng.choice(possible)]

    def answer(
        self,
        word_id: int | str,
        success: bool,
        tested_at: datetime | None = None,
    ) -> Attempt:
        """
        Record one attempt and return it.

        On success the word is complete for this run; on failure it stays
        remaining and its error count increases.
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

        if attempt.success:
            self._remaining.discard(word_id)
        else:
            self._error_count_by_word[word_id] += 1

        return attempt
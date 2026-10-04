from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Word:
    """
    A vocabulary item.

    Parameters
    ----------
    id:
        Stable identifier for the word.
    text:
        Display text for the vocabulary item.
    level:
        Optional CEFR level such as B1, B2, or C1.
    importance:
        Optional weighting used by the selector. Values > 1 increase
        selection priority; values < 1 decrease it.
    """
    id: int | str
    text: str
    level: str = "B1"
    importance: float = 1.0


@dataclass(frozen=True)
class Attempt:
    """
    One binary attempt inside the current run.

    The application owns persistence. To restore a run after restart,
    construct VocabularyRun again with the original words and the attempts
    that already happened.
    """
    word_id: int | str
    success: bool
    tested_at: datetime


@dataclass(frozen=True)
class HistoricalAttempt:
    """
    One binary attempt from any historical run.

    run_id is required so the selector can distinguish first-try success
    from eventual success after one or more failures.
    """
    word_id: int | str
    run_id: int | str
    success: bool
    tested_at: datetime


@dataclass(frozen=True)
class RunStatus:
    total_words: int
    completed_words: int
    remaining_words: int
    attempts: int
    successes: int
    failures: int
    finished: bool


@dataclass(frozen=True)
class WordRunStats:
    word_id: int | str
    attempts: int
    successes: int
    failures: int
    completed: bool

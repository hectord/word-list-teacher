"""AI word-selection strategy: a recency-weighted understanding model.

- ``VocabularyRun``: manages one run (words + attempts) and can be
  reconstructed from them.
- ``VocabularySelector``: uses attempt history across multiple runs to
  estimate understanding and rank / select words for future runs.
"""

from optimizer.models import (
    Attempt,
    HistoricalAttempt,
    RunStatus,
    Word,
    WordRunStats,
)
from optimizer.ai.run import VocabularyRun
from optimizer.ai.selector import VocabularySelector
from optimizer.ai.strategy import AiStrategy

__all__ = [
    "Attempt",
    "HistoricalAttempt",
    "RunStatus",
    "Word",
    "WordRunStats",
    "AiStrategy",
    "VocabularyRun",
    "VocabularySelector",
]
"""Word selection strategies for vocabulary-learning runs.

Two interchangeable strategies are provided as sub-packages of the
abstract ``Strategy`` base class:

- ``optimizer.ai``: the AI strategy — a recency-weighted understanding
  model (``AiStrategy``, composed of ``VocabularyRun`` +
  ``VocabularySelector``).
- ``optimizer.full``: the full strategy — the run mechanics used by the
  application (``FullStrategy``, composed of ``FullRun`` +
  ``FullSelector``).

Both strategies override ``Strategy`` and expose the same select / rank
API, so the application can pick one and use the other interchangeably.
"""

from optimizer.models import (
    Attempt,
    HistoricalAttempt,
    RunStatus,
    Word,
    WordRunStats,
)

from optimizer.strategy import Strategy

from optimizer.ai import AiStrategy, VocabularyRun, VocabularySelector
from optimizer.full import FullRun, FullSelector, FullStrategy

__all__ = [
    "Strategy",
    "Word",
    "Attempt",
    "HistoricalAttempt",
    "RunStatus",
    "WordRunStats",
    "AiStrategy",
    "VocabularyRun",
    "VocabularySelector",
    "FullStrategy",
    "FullRun",
    "FullSelector",
]

__version__ = "0.3.0"
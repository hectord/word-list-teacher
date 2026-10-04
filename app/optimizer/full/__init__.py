"""Full word-selection strategy: the run mechanics used by the
application (a port of ``app/learn.py`` ``Session``).

Same ``Strategy`` API as ``optimizer.ai`` so the two strategies are
interchangeable:

- ``FullStrategy``: the strategy facade (overrides ``Strategy``).
- ``FullRun``: manages one run — every word is asked until it succeeds,
  the next word is picked at random among the remaining ones while
  temporarily skipping the most recently tried words.
- ``FullSelector``: ranks / selects words using the signals the
  application computes from its history (error probability per word and
  mastery through completed runs).
"""

from optimizer.models import (
    Attempt,
    HistoricalAttempt,
    RunStatus,
    Word,
    WordRunStats,
)
from optimizer.full.run import FullRun
from optimizer.full.selector import FullSelector
from optimizer.full.strategy import FullStrategy

__all__ = [
    "Attempt",
    "HistoricalAttempt",
    "RunStatus",
    "Word",
    "WordRunStats",
    "FullStrategy",
    "FullRun",
    "FullSelector",
]
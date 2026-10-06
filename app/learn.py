# -*- coding: utf-8 -*-

from enum import Enum
from typing import TextIO
import re
import unicodedata
from typing import List, Dict, Tuple, Set, Generator, Optional
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from optimizer import (
    AiStrategy,
    Attempt as StrategyAttempt,
    FullStrategy,
    Strategy,
    Word as StrategyWord,
)


# the word-selection strategies a user can follow ('full' is the
# historical behaviour and the default)
STRATEGIES = ('full', 'ai')


def make_strategy(name: Optional[str]) -> Strategy:
    """Build the selection strategy for a user settings value."""
    if name == 'ai':
        return AiStrategy()
    return FullStrategy()


class InvalidFileException(Exception):
    pass


class Language(Enum):
    FRENCH = 1
    ENGLISH = 2
    CHINESE = 3
    GERMAN = 4

    @staticmethod
    def from_code(code: str) -> Optional['Language']:
        for language in Language:
            if language.code == code:
                return language

        return None

    @property
    def code(self) -> str:
        return {
            Language.FRENCH: 'fr',
            Language.ENGLISH: 'en',
            Language.CHINESE: 'cn',
            Language.GERMAN: 'de'
        }.get(self)

    @property
    def name(self) -> str:
        return {
            Language.FRENCH: 'French',
            Language.ENGLISH: 'English',
            Language.CHINESE: 'Chinese',
            Language.GERMAN: 'German'
        }.get(self)


@dataclass(frozen=True)
class User:
    email: str
    password: str
    main_language: Optional[Language]
    level: Optional[str] = None
    target_language: Optional[Language] = None
    # which word-selection strategy the runs of this user follow
    # (see optimizer/): 'full' (default) or 'ai'
    strategy: str = 'full'
    # how many words the AI strategy puts in a run (0/None = all)
    words_per_run: int = 30
    # how many consecutive runs a word must be answered correctly in
    # before it stops being flagged as hard
    hard_runs: int = 2


# levels, ordered from the lowest to the highest
LEVELS = ('B1', 'B2', 'C1')


def included_levels(level: Optional[str]) -> Optional[frozenset]:
    """Levels a learner at ``level`` has to learn (cumulative), or None
    when no level is set.

    Someone at B2 learns the words of B1 and B2.
    """
    if level is None or level not in LEVELS:
        return None

    return frozenset(LEVELS[:LEVELS.index(level) + 1])




REMOVE_PARENTHESIS = re.compile(r'\s*\([^)]*\)\s*')

APOSTROPHES = str.maketrans({
    '\u2019': "'",   # ’
    '\u2018': "'",   # ‘
    '\u02bc': "'",   # ʼ
    '\u2032': "'",   # ′
})


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize('NFKD', text)
    return ''.join(char for char in decomposed
                   if not unicodedata.combining(char))


def normalize(word: str, language: Optional[str] = None) -> str:
    """
    Normalize a word before comparing it with what the user typed.

    Common rules: ignore case, leading/trailing spaces, apostrophe
    variants, '*' and '|' markers, and parenthesised annotations
    (e.g. the German plural "die Beschreibung (-en)").

    Language specific rules (the language being typed):

    * french - ignore accents and elision apostrophes with their
      surrounding spaces ("avoir l’air" == "avoir l' air" == "avoir lair")
    * german - accept "ss" for "ß" and "ae/oe/ue" for "ä/ö/ü",
      so umlauts can be typed on a plain keyboard ("Groesse")
    """
    word = word.strip().lower()
    word = word.translate(APOSTROPHES)
    word = word.replace('|', '').replace('*', '')

    while REMOVE_PARENTHESIS.sub(' ', word) != word:
        word = REMOVE_PARENTHESIS.sub(' ', word)

    word = re.sub(r'\s+', ' ', word).strip()

    language = (language or '').lower()

    if language == 'fr':
        word = _strip_accents(word)
        word = re.sub(r"\s*'\s*", '', word)
    elif language == 'de':
        word = (word.replace('ß', 'ss')
                    .replace('ä', 'ae')
                    .replace('ö', 'oe')
                    .replace('ü', 'ue'))

    # entries are often given with a trailing question mark / period
    return word.rstrip('.,!?;:').strip()


def word_filter(word):
    return normalize(word)


@dataclass(frozen=True)
class Word:
    word_output: str
    word_input: str
    type: Optional[str] = None
    level: Optional[str] = None

    def flip(self) -> 'Word':
        return Word(word_output=self.word_input,
                    word_input=self.word_output,
                    type=self.type,
                    level=self.level)

    @property
    def is_complex(self) -> bool:
        return self.word_output != self._simplified_word_output

    @property
    def key(self) -> str:
        """
        :return: key which group words with same inputs

        A word is considered as "right" if it matches any
         word with the same key in a vocabulary.
        """
        return word_filter(self.word_input)

    @property
    def _simplified_word_output(self) -> str:
        return word_filter(self.word_output)

    def accepts(self, word_output: str,
                language: Optional[str] = None) -> bool:
        return normalize(self.word_output, language) == \
            normalize(word_output, language)

    @property
    def line(self) -> str:
        return f'{self.word_output};{self.word_input}'

    @staticmethod
    def load(line: str):
        line = line.strip()

        word = line.strip().split(';')

        if len(word) != 2:
            error = f'invalid line "{line}"'
            raise InvalidFileException(error)

        word_output, word_input = tuple(word)
        return Word(word_output=word_output,
                    word_input=word_input)


@dataclass(frozen=True)
class WordAttempt:
    success: bool
    word: Word
    typed_word: str
    time: datetime
    example: Optional[str] = None
    input_example: Optional[str] = None


@dataclass(frozen=True)
class Section:
    name: str
    vocabulary: 'Vocabulary'
    id: Optional[int] = None


class Vocabulary:

    def __init__(self,
                 name: Optional[Word] = None,
                 words: List[Word] = None,
                 input_language: str = None,
                 output_language: str = None,
                 flipped: bool = False,
                 sections: List[Optional[str]] = None,
                 section_ids: Dict[str, int] = None):
        self._name = name
        self._words = []
        self._word_sections = []

        self._similar_words = None
        self._id = None
        self._word_ids = {}
        self._flipped = flipped
        self._input_language = input_language
        self._output_language = output_language
        self._section_ids = dict(section_ids or {})
        self._examples = {}
        self._input_examples = {}

        for i, word in enumerate(words or []):
            section = sections[i] if sections is not None else None
            self.add_word(word, section=section)

    def add_word(self, word: Word,
                 word_id: Optional[int] = None,
                 section: Optional[str] = None):
        self._words.append(word)
        self._word_sections.append(section)
        if word_id is not None:
            self._word_ids[word] = word_id
        self._similar_words = None   # rebuilt lazily

    @property
    def is_flipped(self) -> bool:
        return self._flipped

    def similar_words(self, word: Word) -> Set[Word]:
        # the index is built on demand: building it eagerly costs a
        # normalisation for every word, which matters for big
        # vocabularies which are only counted (e.g. the index page)
        if self._similar_words is None:
            similar = defaultdict(set)
            for this_word in self._words:
                similar[this_word.key].add(this_word)
            self._similar_words = similar

        return self._similar_words[word.key]

    def section_of(self, word: Word) -> Optional[str]:
        try:
            return self._word_sections[self._words.index(word)]
        except ValueError:
            return None

    @property
    def word_sections(self) -> List[Optional[str]]:
        """Section of each word, aligned with ``words`` (by index)."""
        return self._word_sections.copy()

    def set_section_ids(self, section_ids: Dict[str, int]):
        self._section_ids = dict(section_ids or {})

    def section_id(self, name: str) -> Optional[int]:
        return self._section_ids.get(name)

    def section_name_for_id(self, section_id: int) -> Optional[str]:
        for name, this_id in self._section_ids.items():
            if this_id == section_id:
                return name
        return None

    def section_by_id(self, section_id: int) -> Optional['Vocabulary']:
        name = self.section_name_for_id(section_id)
        if name is None:
            return None
        return self.section(name)

    def set_example(self, word: Word, example: Optional[str]):
        if example is not None:
            self._examples[word] = example

    def example(self, word: Word) -> Optional[str]:
        return self._examples.get(word)

    def set_input_example(self, word: Word, example: Optional[str]):
        """Example sentence in the vocabulary's input language (the
        learner's own language), shown on request while learning."""
        if example is not None:
            self._input_examples[word] = example

    def input_example(self, word: Word) -> Optional[str]:
        return self._input_examples.get(word)

    def select_ids(self, ids) -> 'Vocabulary':
        """A copy restricted to the given word ids (the AI strategy
        selects which words compose a run). The section of each kept word
        and all metadata (ids, examples) are preserved."""
        wanted = set(ids)
        words = []
        sub_sections = []

        for word, section in zip(self._words, self._word_sections):
            if self._word_ids.get(word) in wanted:
                words.append(word)
                sub_sections.append(section)

        voc = Vocabulary(self._name, words, self._input_language,
                         self._output_language, self._flipped,
                         sections=sub_sections,
                         section_ids=self._section_ids)
        voc.set_id(self._id)

        for word in words:
            word_id = self._word_ids.get(word)
            if word_id is not None:
                voc.set_word_id(word, word_id)
            voc.set_example(word, self.example(word))
            voc.set_input_example(word, self.input_example(word))

        return voc

    def section(self, name: str) -> Optional['Vocabulary']:
        """Return a vocabulary restricted to one section (with word IDs)."""
        words = []
        sub_sections = []

        for word, section in zip(self._words, self._word_sections):
            if section == name:
                words.append(word)
                sub_sections.append(section)

        if not words:
            return None

        voc = Vocabulary(self._name, words,
                         self._input_language,
                         self._output_language,
                         self._flipped,
                         sections=sub_sections,
                         section_ids=self._section_ids)
        voc.set_id(self._id)

        for word in words:
            word_id = self._word_ids.get(word)
            if word_id is not None:
                voc.set_word_id(word, word_id)
            voc.set_example(word, self.example(word))
            voc.set_input_example(word, self.input_example(word))

        return voc

    @property
    def sections(self) -> List[Section]:
        """Ordered list of non-empty sections (Section name + vocabulary)."""
        result = []
        seen = set()

        for name in self._word_sections:
            if name is None or name in seen:
                continue
            seen.add(name)
            section_voc = self.section(name)
            if section_voc is not None:
                result.append(Section(name, section_voc,
                                      self._section_ids.get(name)))

        return result

    def flip(self) -> 'Vocabulary':
        name = None if self._name is None else self._name.flip()
        words = []

        for word in self._words:
            words.append(word.flip())

        voc = Vocabulary(name, words,
                         self.output_language,
                         self.input_language,
                         not self.is_flipped,
                         sections=list(self._word_sections),
                         section_ids=self._section_ids)
        voc.set_id(self._id)

        for word in self._words:
            word_id = self._word_ids.get(word)
            if word_id is not None:
                voc.set_word_id(word.flip(), word_id)
            voc.set_example(word.flip(), self.example(word))
            voc.set_input_example(word.flip(), self.input_example(word))

        return voc

    @property
    def id(self) -> Optional[int]:
        return self._id

    @property
    def input_language(self) -> Optional[str]:
        return self._input_language

    @property
    def output_language(self) -> Optional[str]:
        return self._output_language

    def set_id(self, id: int):
        self._id = id

    def set_word_id(self, word: Word, word_id: int):
        self._word_ids[word] = word_id

    def word_id(self, word: Word) -> Optional[int]:
        return self._word_ids.get(word)

    def word(self, word_id: int) -> Optional[Word]:
        for this_word, this_word_id in self._word_ids.items():
            if word_id == this_word_id:
                return this_word
        return None

    def add(self, other: 'Vocabulary'):
        # inherit the metadata when merging into an empty vocabulary
        # (sessions are rebuilt from the database this way)
        if self._input_language is None:
            self._input_language = other._input_language
        if self._output_language is None:
            self._output_language = other._output_language
        if self._id is None:
            self._id = other._id

        self._words.extend(other._words)
        self._word_sections.extend(other._word_sections)
        self._section_ids.update(other._section_ids)
        self._examples.update(other._examples)
        self._input_examples.update(other._input_examples)
        self._word_ids.update(other._word_ids)

        # the similar-words index is rebuilt lazily
        self._similar_words = None

    def __str__(self) -> str:
        if self.name is None:
            return 'unknown'
        else:
            return self.name.word_input

    @property
    def name(self) -> Word:
        return self._name

    def _name_word(self) -> Optional[str]:
        """Persistable vocabulary name (or None)."""
        if self._name is None:
            return None
        return self._name.word_input

    def __iter__(self) -> Generator[Word, None, None]:
        for word in self._words:
            yield word

    def __len__(self) -> int:
        return len(self._words)

    @property
    def words(self) -> List[Word]:
        return self._words.copy()

    @staticmethod
    def _directive(line: str) -> Optional[str]:

        if not line.startswith('#'):
            return None

        if ' ' not in line:
            return line
        else:
            i = line.index(' ')
            return line[:i]

    @staticmethod
    def _after_directive(line: str) -> Optional[str]:
        i = line.index(' ')
        return line[i:].strip()

    @staticmethod
    def load(file_input: TextIO):
        words = []
        word_sections = []
        name = None
        input_language = None
        output_language = None
        current_section = None

        for line in file_input.readlines():
            line = line.strip()

            if not line:
                continue

            directive = Vocabulary._directive(line)

            if directive == '#input':
                input_language = Vocabulary._after_directive(line)
            elif directive == '#output':
                output_language = Vocabulary._after_directive(line)
            elif directive == '#section':
                current_section = Vocabulary._after_directive(line)
            else:
                if directive == '#name':
                    line = Vocabulary._after_directive(line)

                word = Word.load(line)
                if directive == '#name':
                    name = word
                words.append(word)
                word_sections.append(current_section)

        return Vocabulary(name, words,
                          input_language,
                          output_language,
                          sections=word_sections)


class VocabularyStats:
    """Per-word practice statistics: how reliably the learner knows each
    word (mastery) and whether it is currently flagged as hard.

    * mastery: share of runs where the word was answered correctly on
      its first attempt (100 = never missed it, 0 = never got it
      right);
    * hard: the word was answered wrongly at least once during the
      last ``hard_runs`` runs which included it.
    """

    def __init__(self,
                 v: Vocabulary,
                 mastery_by_word: Dict[Word, float],
                 hard_words=()):
        self._v = v
        self._mastery_by_word = mastery_by_word
        self._hard_words = frozenset(hard_words)

    def mastery_for(self, w: Word):
        """The 0-100 mastery percentage of ``w`` (0.0 when it was never
        part of a run)."""
        return self._mastery_by_word.get(w, 0.0)

    def included_for(self, w: Word):
        """True when ``w`` was part of at least one run."""
        return w in self._mastery_by_word

    def hard_for(self, w: Word):
        """True when ``w`` was answered wrongly during at least one of
        the last ``hard_runs`` runs which included it."""
        return w in self._hard_words


class Session:
    # the run mechanics (which word to ask next) come from the strategy
    # in optimizer/ (the full strategy keeps the historical behaviour:
    # cooldown of 4, uniform random among the remaining words)

    def __init__(self,
                 attempts: List[WordAttempt],
                 vocabulary: Vocabulary,
                 current_word: Word = None,
                 strategy: "Strategy" = None,
                 strategy_name: str = None):
        self._attempts = attempts
        self._vocabulary = vocabulary
        self.strategy = strategy or FullStrategy()
        if strategy_name is None:
            strategy_name = ('ai' if isinstance(self.strategy, AiStrategy)
                             else 'full')
        # which algorithm drives this run ('full' or 'ai')
        self.strategy_name = strategy_name

        # map the application words to the strategy words (real word ids
        # when available, a stable per-position id otherwise)
        self._word_to_id = {}
        self._id_to_word = {}
        for index, word in enumerate(vocabulary.words):
            word_id = vocabulary.word_id(word)
            if word_id is None:
                word_id = '#%d' % index
            self._word_to_id[word] = word_id
            self._id_to_word[word_id] = word

        self._run = self.strategy.create_run(
            [StrategyWord(id=self._word_to_id[w],
                          text=w.word_output,
                          level=w.level or 'B1')
             for w in self._word_to_id],
            [StrategyAttempt(word_id=self._word_to_id[a.word],
                             success=a.success,
                             tested_at=a.time)
             for a in attempts],
        )

        self._current_word = current_word
        if self._current_word is None:
            self._pick_next_word()
        assert self._current_word is None or \
            self._word_to_id[self._current_word] in \
            self._run.remaining_word_ids
        self._id = None

    @property
    def vocabulary(self) -> Vocabulary:
        return self._vocabulary

    @property
    def is_flipped(self) -> bool:
        return self._vocabulary.is_flipped

    @property
    def id(self) -> int:
        return self._id

    @property
    def attempts(self) -> List[WordAttempt]:
        return self._attempts

    def set_id(self, id: int):
        self._id = id

    def _pick_next_word(self):
        selected = self._run.next_word()
        self._current_word = None if selected is None \
            else self._id_to_word[selected.id]

    def _failure_counts(self) -> dict:
        """Number of failures per run word (any strategy: both runs
        expose ``stats(word_id).failures``)."""
        return {
            word.id: self._run.stats(word.id).failures
            for word in self._run.words
        }

    @property
    def vocabulary_left(self) -> Vocabulary:
        failures = self._failure_counts()
        ranked = sorted(
            (word_id for word_id, count in failures.items() if count > 0),
            key=lambda word_id: -failures[word_id],
        )
        words = [self._id_to_word[word_id] for word_id in ranked]

        return Vocabulary(None, words,
                          self.vocabulary.input_language,
                          self.vocabulary.output_language)

    @property
    def new_words_learned(self) -> int:
        """Words without any failure in this run."""
        failures = self._failure_counts()
        return sum(1 for count in failures.values() if count == 0)

    @property
    def accuracy(self) -> float:
        """Share of the tested words without any error (0..100)."""
        failures = self._failure_counts()
        remaining = set(self._run.remaining_word_ids)

        word_in_error = sum(1 for count in failures.values() if count > 0)
        untested = sum(1 for word_id, count in failures.items()
                       if count == 0 and word_id in remaining)

        tested = len(failures) - untested
        if not tested:
            return 100.0
        return 100.0 - word_in_error / tested * 100.0

    @property
    def run(self):
        """The strategy run behind this session (stats, per-word info)."""
        return self._run

    def summary(self, understand: Dict = None) -> Dict:
        """Numeric summary of the run (statistics only, no word lists).

        ``understand`` is an optional {strategy word id: understanding}
        map (the AI strategy): the summary then also reports the model
        statistics.
        """
        status = self._run.status()

        failures = self._failure_counts()

        ret = {
            'strategy': self.strategy_name,
            'words': status.total_words,
            'attempts': status.attempts,
            'successes': status.successes,
            'failures': status.failures,
            'accuracy': round(self.accuracy, 1),
            'new_words': sum(1 for count in failures.values()
                             if count == 0),
            'words_to_review': sum(1 for count in failures.values()
                                   if count > 0),
        }

        if understand:
            scores = list(understand.values())
            if scores:
                ret['avg_understanding'] = \
                    round(100.0 * sum(scores) / len(scores), 1)
                ret['min_understanding'] = round(100.0 * min(scores), 1)
                ret['weak_words'] = sum(1 for score in scores
                                        if score < 0.5)
                ret['mastered_words'] = sum(1 for score in scores
                                            if score >= 0.7)

        return ret

    @property
    def current_word(self) -> Optional[Word]:
        return self._current_word

    def guess(self, word: Word, word_output: str) -> Optional[WordAttempt]:

        current_word = self.current_word
        if word != self._current_word:
            word_id = self._word_to_id.get(word)
            if word_id is None or \
                    word_id not in self._run.remaining_word_ids:
                return None
            current_word = word

        # find a word which matches (the answer is written in the
        # vocabulary's output language, so use its comparison rules)
        output_language = self.vocabulary.output_language
        for word in self.vocabulary.similar_words(current_word):
            if word.accepts(word_output, output_language):
                success = True
                break
        else:
            success = False

        attempt = WordAttempt(word=current_word,
                              typed_word=word_output,
                              success=success,
                              time=datetime.now(),
                              example=self.vocabulary.example(current_word),
                              input_example=self.vocabulary.input_example(
                                  current_word))
        self._attempts.append(attempt)

        self._run.answer(self._word_to_id[current_word], success)
        self._pick_next_word()

        return attempt

    @property
    def is_finished(self) -> bool:
        return self._current_word is None

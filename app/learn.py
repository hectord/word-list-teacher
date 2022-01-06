# -*- coding: utf-8 -*-

from enum import Enum
import re
from typing import List, Dict, Tuple, Set, Generator, Optional
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import random


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
    languages_spoken: Set[Language]


def filter(word):
    word = word.replace('|', '').replace('*', '')

    if '(' in word:
        word = re.sub('\s*\([^)]*\)$', '', word)

    return word.strip()


@dataclass(frozen=True)
class Word:
    word_output: str
    word_input: str
    directive: Optional[str]

    def flip(self) -> 'Word':
        return Word(word_output=self.word_input,
                    word_input=self.word_output,
                    directive=self.directive)

    @property
    def is_complex(self) -> bool:
        return self.word_output != self._simplified_word_output

    @property
    def is_name(self) -> Optional[str]:
        return self.directive == '#name'

    @property
    def _simplified_word_output(self) -> str:
        simple_german = self.word_output.lower()
        return filter(simple_german)

    def accepts(self, word_output: str) -> bool:
        return self._simplified_word_output == word_output.lower()

    @property
    def line(self) -> str:
        word_line = f'{self.word_output};{self.word_input}'

        if self.directive is not None:
            word_line = f'{self.directive} {word_line}'

        return word_line

    @staticmethod
    def load(line: str, directive: str = None):
        line = line.strip()

        word = line.strip().split(';')

        if len(word) != 2:
            error = f'invalid line "{line}"'
            raise InvalidFileException(error)

        word_output, word_input = tuple(word)
        return Word(directive=directive,
                    word_output=word_output,
                    word_input=word_input)


@dataclass(frozen=True)
class WordAttempt:
    success: bool
    word: Word
    typed_word: str
    time: datetime


class Vocabulary:

    def __init__(self,
                 name: Optional[Word] = None,
                 words: List[Word] = None,
                 input_language: str = None,
                 output_language: str = None,
                 flipped: bool = False):
        self._name = name
        self._words = words or []
        self._id = None
        self._flipped = flipped
        self._input_language = input_language
        self._output_language = output_language

    @property
    def is_flipped(self) -> bool:
        return self._flipped

    def flip(self) -> 'Vocabulary':
        name = None if self._name is None else self._name.flip()
        words = []

        for word in self._words:
            words.append(word.flip())

        voc = Vocabulary(name, words,
                         self.output_language,
                         self.input_language,
                         not self.is_flipped)
        voc.set_id(self._id)
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

    def add(self, other: 'Vocabulary'):
        self._words.extend(other._words)

    def __str__(self) -> str:
        if self.name is None:
            return 'unknown'
        else:
            return self.name.word_input

    @property
    def name(self) -> Word:
        return self._name

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
    def load(filename: str):
        words = []
        name = None
        from_language = None
        to_language = None

        with open(filename, 'r') as f:
            for line in f.readlines():
                line = line.strip()

                if not line:
                    continue

                directive = Vocabulary._directive(line)

                if directive == '#input':
                    input_language = Vocabulary._after_directive(line)
                elif directive == '#output':
                    output_language = Vocabulary._after_directive(line)
                else:
                    if directive == '#name':
                        line = Vocabulary._after_directive(line)

                    word = Word.load(line, directive)
                    if directive == '#name':
                        name = word
                    words.append(word)

        return Vocabulary(name, words,
                          input_language,
                          output_language)


class VocabularyStats:

    def __init__(self,
                 v: Vocabulary,
                 errors_prob_by_word: Dict[Word, int]):
        self._v = v
        self._errors_prob_by_word = errors_prob_by_word

    def errors_prob_for(self, w: Word):
        return self._errors_prob_by_word.get(w, 0.0)


class Session:

    def __init__(self,
                 attempts: List[WordAttempt],
                 vocabulary: Vocabulary,
                 current_word: Word = None):
        self._attempts = attempts
        self._vocabulary = vocabulary

        self._error_count_by_word = defaultdict(int)

        self._nok_words = vocabulary.words
        for attempt in attempts:
            word = attempt.word

            if attempt.success:
                self._nok_words.remove(word)
            else:
                self._error_count_by_word[word] += 1

        self._current_word = current_word
        if self._current_word is None:
            self._pick_next_word()
        assert self._current_word is None or self._current_word in self._nok_words
        self._id = None

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

        if self._nok_words:
            possible_words = list(self._nok_words)
            if (self._current_word is not None and
                    possible_words != [self._current_word]):
                possible_words.remove(self._current_word)
            self._current_word = random.choice(possible_words)
        else:
            self._current_word = None

    @property
    def vocabulary_left(self) -> Vocabulary:
        word_count_list = list(self._error_count_by_word.items())
        word_count_list.sort(key=lambda x: -x[1])
        words = set()

        for word, _ in word_count_list:
            words.add(word)

        return Vocabulary(None, words,
                          self._from_language,
                          self._to_language)

    @property
    def new_words_learned(self) -> int:
        return len(self._vocabulary) - len(self._error_count_by_word)

    @property
    def accuracy(self) -> float:
        word_in_error = len(self._error_count_by_word)

        untested_words = set(self._nok_words) - set(self._error_count_by_word)
        return 100.0 - word_in_error / (len(self._vocabulary) - len(untested_words)) * 100.0

    @property
    def current_word(self) -> Optional[Word]:
        return self._current_word

    def guess(self, word_output: str) -> WordAttempt:
        current_word = self.current_word

        success = current_word.accepts(word_output)

        attempt = WordAttempt(word=current_word,
                              typed_word=word_output,
                              success=success,
                              time=datetime.now())
        self._attempts.append(attempt)

        if success:
            self._nok_words.remove(current_word)
            self._current_word = None
            self._pick_next_word()
        else:
            self._error_count_by_word[current_word] += 1
            self._pick_next_word()

        return attempt

    @property
    def is_finished(self) -> bool:
        return self._current_word is None

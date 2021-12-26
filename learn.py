# -*- coding: utf-8 -*-

import re
from typing import List, Dict, Tuple, Set, Generator, Optional
from collections import defaultdict
from dataclasses import dataclass
import random


class InvalidFileException(Exception):
    pass


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
    def load(line: str):
        line = line.strip()
        directive = None

        if line.startswith('#') and ' ' in line:
            i = line.index(' ')
            directive = line[:i]
            line = line[i:]

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
    word: Word
    typed_word_output: str


class Vocabulary:

    def __init__(self,
                 name: Optional[Word] = None,
                 words: Set[Word] = None):
        self._name = name
        self._words = words or set()
        self._id = None

    @property
    def id(self) -> Optional[int]:
        return self._id

    def set_id(self, id: int):
        self._id = id

    def add(self, other: 'Vocabulary'):
        self._words.update(other._words)

    def __str__(self) -> str:
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
    def words(self) -> Set[Word]:
        return self._words.copy()

    @staticmethod
    def load(filename: str):
        words = set()
        name = None

        with open(filename, 'r') as f:
            for line in f.readlines():
                if line.strip():
                    word = Word.load(line)
                    if word.is_name:
                        name = word
                    words.add(word)

        return Vocabulary(name, words)


class LearnEngine:

    def __init__(self,
                 attempts: List[WordAttempt],
                 vocabulary: Vocabulary):
        self._attempts = attempts
        self._vocabulary = vocabulary

        self._error_count_by_word = defaultdict(int)
        self._nok_words = vocabulary.words
        self._error_by_word = {}

        self._current_word = None
        self._pick_next_word()
        self._id = None

    @property
    def id(self) -> int:
        return self._id

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

        return Vocabulary(None, words)

    @property
    def new_words_learned(self) -> int:
        return len(self._vocabulary) - len(self._error_count_by_word)

    @property
    def accuracy(self) -> float:
        errors = sum(self._error_count_by_word.values())
        attempts = len(self._vocabulary) + errors
        return len(self._vocabulary) / attempts

    @property
    def current_word(self) -> Optional[Word]:
        return self._current_word

    def guess(self, word_output: str) -> bool:
        current_word = self.current_word

        attempt = WordAttempt(word=current_word,
                              typed_word_output=word_output)
        self._attempts.append(attempt)

        if current_word.accepts(word_output):
            self._nok_words.remove(current_word)
            self._current_word = None
            self._pick_next_word()
            return True
        else:
            self._error_count_by_word[current_word] += 1
            self._pick_next_word()
            return False

    @property
    def is_finished(self) -> bool:
        return self._current_word is None

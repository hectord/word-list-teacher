# -*- coding: utf-8 -*-

import unittest

from store import load_database
from learn import Vocabulary, Word


class TestStore(unittest.TestCase):

    def test_ok(self):
        db = load_database(':memory:')

        word1 = Word(word_input='de_1',
                     word_output='fr_1',
                     directive=None)
        word2 = Word(word_input='de_2',
                     word_output='fr_2',
                     directive=None)
        words = {word1, word2}

        new_voc = Vocabulary(word1, words)

        db.create_vocabulary(new_voc)

        vocs = db.list_vocabularies().values()
        self.assertEqual(1, len(vocs))
        self.assertEqual({word1, word2},
                         next(iter(vocs)).words)

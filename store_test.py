# -*- coding: utf-8 -*-

import unittest

from store import load_database, DbException
from learn import Vocabulary, Word


class TestStore(unittest.TestCase):

    def test_voc(self):
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

        voc2 = db.get_vocabulary(1)
        self.assertEqual({word1, word2},
                         voc2.words)

    def test_user(self):
        db = load_database(':memory:')

        new_user = db.create_user('test@hotmail.com', 'abc')
        self.assertIsNotNone(new_user)

        with self.assertRaises(DbException):
            db.create_user('test@hotmail.com', 'other')

        with self.assertRaises(DbException):
            db.get_user('test2@gmail.com', 'def')

        with self.assertRaises(DbException):
            db.get_user('test@hotmail.com', 'def')

        user = db.get_user('test@hotmail.com', 'abc')
        self.assertEqual('test@hotmail.com', user.email)

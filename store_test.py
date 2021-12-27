# -*- coding: utf-8 -*-

import unittest

from store import load_database, DbException
from learn import Vocabulary, Word


class TestStore(unittest.TestCase):

    def setUp(self):
        self.db = load_database(':memory:')

    def _create_vocabulary(self):

        self.word1 = Word(word_input='de_1',
                          word_output='fr_1',
                          directive=None)
        self.word2 = Word(word_input='de_2',
                          word_output='fr_2',
                          directive=None)
        self.words = {self.word1, self.word2}

        self.new_voc = Vocabulary(self.word1, self.words)

        voc_id = self.db.create_vocabulary(self.new_voc)
        self.assertEqual(1, voc_id)

    def _create_user(self):
        self.user = self.db.create_user('test@hotmail.com', 'abc')

    def test_voc(self):
        self._create_vocabulary()

        vocs = self.db.list_vocabularies().values()
        self.assertEqual(1, len(vocs))
        self.assertEqual({self.word1, self.word2},
                         next(iter(vocs)).words)

        voc2 = self.db.get_vocabulary(1)
        self.assertEqual({self.word1, self.word2},
                         voc2.words)

    def test_manage_sessions(self):
        self._create_vocabulary()
        self._create_user()

        self.assertIsNone(self.db.last_session(self.user, self.new_voc))

        session_id = self.db.create_new_session(self.user, self.new_voc)
        self.assertIsNotNone(session_id)

        session = self.db.last_session(self.user, self.new_voc)
        self.assertEqual(session_id, session.id)

        self.assertTrue((self.word1 == session.current_word) or
                        (self.word2 == session.current_word))

        word_attempt = session.guess('ok')

        self.db.add_word(session, word_attempt)

        db_session = self.db.load_session(session.id)

    def test_user(self):
        self._create_user()
        self.assertIsNotNone(self.user)

        with self.assertRaises(DbException):
            self.db.create_user('test@hotmail.com', 'other')

        with self.assertRaises(DbException):
            self.db.get_user('test2@gmail.com', 'def')

        with self.assertRaises(DbException):
            self.db.get_user('test@hotmail.com', 'def')

        other_user = self.db.get_user('test@hotmail.com', 'abc')
        self.assertEqual('test@hotmail.com', other_user.email)

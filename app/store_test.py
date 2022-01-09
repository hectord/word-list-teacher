# -*- coding: utf-8 -*-

import unittest

from typing import Set

from store import load_database, DbException
from learn import Vocabulary, Word, Language


class TestStore(unittest.TestCase):

    def setUp(self):
        self.db = load_database(':memory:')

        for language in Language:
            self.db.create_language(language)

    def _create_vocabulary(self):

        self.word1 = Word(word_input='fr_1',
                          word_output='de_1',
                          directive=None)
        self.word2 = Word(word_input='fr_2',
                          word_output='de_2',
                          directive=None)
        self.words = [self.word1, self.word2]

        self.new_voc = Vocabulary(self.word1, self.words,
                                  input_language='fr',
                                  output_language='de')

        voc_id = self.db.create_vocabulary(self.new_voc)
        self.assertEqual(1, voc_id)

    def _create_user(self, languages: Set[Language] = None):
        if languages is None:
            languages = {Language.FRENCH, Language.CHINESE}
        self.user = self.db.create_user('test@hotmail.com', 'abc',
                                        languages)

    def test_voc(self):
        self._create_vocabulary()
        self._create_user()

        vocs = self.db.list_vocabularies(self.user).values()
        self.assertEqual(1, len(vocs))

        self.assertEqual([self.word1, self.word2],
                         next(iter(vocs)).words)

        voc2 = self.db.get_vocabulary(self.user, 1)
        self.assertEqual([self.word1, self.word2],
                         voc2.words)

    def test_manage_sessions(self):
        self._create_vocabulary()
        self._create_user()

        self.assertIsNone(self.db.last_session(self.user, self.new_voc))

        session_id = self.db.create_new_session(self.user, self.new_voc)
        self.assertIsNotNone(session_id)

        session = self.db.last_session(self.user, self.new_voc)
        self.assertEqual(session_id.id, session.id)

        first_word = session.current_word

        self.assertTrue((self.word1 == session.current_word) or
                        (self.word2 == session.current_word))

        word_attempt = session.guess(session.current_word,
                                     session.current_word.word_output)
        self.db.add_word(session, word_attempt)

        db_session = self.db.load_session(session.id)
        self.assertNotEqual(first_word, db_session.current_word)
        self.assertFalse(db_session.is_finished)

        self.assertIsNone(self.db.last_session(self.user, self.new_voc,
                                               finished=True))
        self.assertIsNotNone(self.db.last_session(self.user, self.new_voc,
                                                  finished=False))

        word_attempt = session.guess(session.current_word,
                                     session.current_word.word_output)
        self.db.add_word(session, word_attempt)

        db_session = self.db.load_session(session.id)
        self.assertTrue(db_session.is_finished)
        self.assertEqual(100.0, db_session.accuracy)

        self.assertIsNone(self.db.last_session(self.user, self.new_voc,
                                               finished=False))
        self.assertIsNotNone(self.db.last_session(self.user, self.new_voc,
                                                  finished=True))

    def test_vocabulary_stats(self):
        self._create_user()
        self._create_vocabulary()

        new_session = self.db.create_new_session(self.user, self.new_voc)

        word = new_session.current_word
        attempt = new_session.guess(word, 'bla')

        self.db.add_word(new_session, attempt)

        other_word = new_session.current_word

        stats = self.db.vocabulary_stats(self.new_voc)

        self.assertEqual(100.0, stats.errors_prob_for(word))
        self.assertEqual(0.0, stats.errors_prob_for(other_word))

    def test_user(self):
        self._create_user()
        self.assertIsNotNone(self.user)

        with self.assertRaises(DbException):
            self.db.create_user('test@hotmail.com', 'other', set())

        with self.assertRaises(DbException):
            self.db.get_user('test2@gmail.com', 'def')

        with self.assertRaises(DbException):
            self.db.get_user('test@hotmail.com', 'def')

        other_user = self.db.get_user('test@hotmail.com', 'abc')
        self.assertEqual('test@hotmail.com', other_user.email)


    def test_normal_vocabulary(self):
        self._create_vocabulary()
        self._create_user({Language.FRENCH})

        vocs = self.db.list_vocabularies(self.user)

        self.assertEqual(1, len(vocs))
        first_voc = next(iter(vocs.values()))
        self.assertFalse(first_voc.is_flipped)

        first_voc = self.db.get_vocabulary(self.user, first_voc.id)

        self.assertFalse(first_voc.is_flipped)
        self.assertEqual('fr', first_voc.input_language)
        self.assertEqual('de', first_voc.output_language)

        self.assertEqual([self.word1, self.word2],
                          first_voc.words)

        new_session = self.db.create_new_session(self.user, first_voc)
        self.assertFalse(new_session.is_flipped)

        self.assertIn(new_session.current_word,
                      {self.word1, self.word2})

        session_fetched = self.db.last_session(self.user, first_voc)

        self.assertIn(session_fetched.current_word,
                      {self.word1, self.word2})

        session_fetched2 = self.db.load_session(session_fetched.id)
        self.assertIn(session_fetched2.current_word,
                      {self.word1, self.word2})

        current_word = session_fetched.current_word
        attempt = session_fetched.guess(current_word, current_word.word_input)

        self.db.add_word(session_fetched, attempt)

    def test_flipped_vocabulary(self):
        self._create_vocabulary()
        self._create_user({Language.GERMAN})

        vocs = self.db.list_vocabularies(self.user)

        self.assertEqual(1, len(vocs))
        first_voc = next(iter(vocs.values()))

        first_voc = self.db.get_vocabulary(self.user, first_voc.id)

        self.assertTrue(first_voc.is_flipped)
        self.assertEqual('de', first_voc.input_language)
        self.assertEqual('fr', first_voc.output_language)

        self.assertEqual([self.word1.flip(), self.word2.flip()],
                          first_voc.words)

        new_session = self.db.create_new_session(self.user, first_voc)

        self.assertIn(new_session.current_word,
                      {self.word1.flip(), self.word2.flip()})
        self.assertTrue(new_session.is_flipped)

        self.assertTrue(first_voc.is_flipped)
        session_fetched = self.db.last_session(self.user, first_voc)
        self.assertTrue(session_fetched.is_flipped)

        self.assertIn(session_fetched.current_word,
                      {self.word1.flip(), self.word2.flip()})

        session_fetched2 = self.db.load_session(session_fetched.id)
        self.assertIn(session_fetched2.current_word,
                      {self.word1.flip(), self.word2.flip()})

        current_word = session_fetched.current_word
        attempt = session_fetched.guess(current_word, current_word.word_input)

        self.db.add_word(session_fetched, attempt)

    def test_list_vocabulary(self):
        self._create_vocabulary()
        self._create_user()

        vocs = self.db.list_vocabularies_for(None)

        self.assertEqual({1}, vocs.keys())
        voc = next(iter(vocs.values()))

        self.assertEqual(self.new_voc.words, voc.words)

        self.assertIsNone(self.db.get_vocabulary(None, 2))
        self.assertEqual([self.word1, self.word2],
                         self.db.get_vocabulary(None, 1).words)

    def test_same_name_several_times(self):

        word1 = Word(word_input='fr_1',
                     word_output='de_1',
                     directive=None)
        word2 = Word(word_input='fr_1',
                     word_output='de_1',
                     directive='#name')
        words = [word1, word2]

        new_voc = Vocabulary(word1, words,
                             input_language='fr',
                             output_language='de')
        self._create_user()

        self.db.create_vocabulary(new_voc)

        self.db.create_new_session(self.user, new_voc)
        session = self.db.last_session(self.user, new_voc)

        word_attempt = session.guess(word2, word2.word_output)
        self.db.add_word(session, word_attempt)

        self.assertTrue(word_attempt.success)
        self.db.last_session(self.user, new_voc)

    def test_remove_vocabulary(self):
        self._create_vocabulary()
        self._create_user()

        self.db.create_new_session(self.user, self.new_voc)
        session = self.db.last_session(self.user, self.new_voc)
        session.guess(self.word1, self.word1.word_output)

        self.db.remove_vocabulary(self.new_voc)

        self.assertEqual({}, self.db.list_vocabularies(None))


if __name__ == '__main__':
    unittest.main(verbosity=3)

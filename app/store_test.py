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
        self.assertEqual('fr_1', voc2.name.word_input)

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
        self.db.add_word_attempt(session, word_attempt)

        db_session = self.db.load_session(session.id)
        self.assertNotEqual(first_word, db_session.current_word)
        self.assertFalse(db_session.is_finished)

        self.assertIsNone(self.db.last_session(self.user, self.new_voc,
                                               finished=True))
        self.assertIsNotNone(self.db.last_session(self.user, self.new_voc,
                                                  finished=False))

        word_attempt = session.guess(session.current_word,
                                     session.current_word.word_output)
        self.db.add_word_attempt(session, word_attempt)

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

        self.db.add_word_attempt(new_session, attempt)

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

        self.db.add_word_attempt(session_fetched, attempt)

    def _create_sectioned_vocabulary(self):
        self.sec_words = [Word(word_input='en_1', word_output='fr_1',
                               directive=None),
                          Word(word_input='en_2', word_output='fr_2',
                               directive=None),
                          Word(word_input='en_3', word_output='fr_3',
                               directive=None)]

        self.sec_voc = Vocabulary(self.sec_words[0], self.sec_words,
                                  input_language='en',
                                  output_language='fr',
                                  sections=['A', 'A', 'B'])

        return self.db.create_vocabulary(self.sec_voc)

    def test_section_persistence(self):
        voc_id = self._create_sectioned_vocabulary()
        self._create_user({Language.ENGLISH})

        voc = self.db.get_vocabulary(self.user, voc_id)

        self.assertEqual(['A', 'B'], [s.name for s in voc.sections])
        self.assertEqual('A', voc.section_of(voc.words[0]))
        self.assertEqual('B', voc.section_of(voc.words[2]))

    def test_section_session(self):
        voc_id = self._create_sectioned_vocabulary()
        self._create_user({Language.ENGLISH})

        voc = self.db.get_vocabulary(self.user, voc_id)

        with self.assertRaises(DbException):
            self.db.create_new_session(self.user, voc, section='Nope')

        whole_session = self.db.create_new_session(self.user, voc)
        section_session = self.db.create_new_session(self.user, voc,
                                                     section='A')

        self.assertEqual(3, len(whole_session.vocabulary))
        self.assertEqual(2, len(section_session.vocabulary))
        self.assertEqual(['A', 'A'],
                         [voc.section_of(w) for w in section_session.vocabulary.words])

        self.assertEqual(whole_session.id,
                         self.db.last_session(self.user, voc, section='').id)
        self.assertEqual(section_session.id,
                         self.db.last_session(self.user, voc, section='A').id)

        attempt = whole_session.guess(whole_session.current_word,
                                      whole_session.current_word.word_output)
        self.db.add_word_attempt(whole_session, attempt)
        attempt = section_session.guess(section_session.current_word,
                                        section_session.current_word.word_output)
        self.db.add_word_attempt(section_session, attempt)

        reloaded = self.db.load_session(section_session.id)
        self.assertEqual(2, len(reloaded.vocabulary))
        self.assertEqual(1, len(reloaded.attempts))
        self.assertFalse(reloaded.is_finished)

    def test_section_flipped(self):
        voc_id = self._create_sectioned_vocabulary()
        # user speaks French -> fr/en vocab is flipped
        self._create_user({Language.FRENCH})

        voc = self.db.get_vocabulary(self.user, voc_id)
        self.assertTrue(voc.is_flipped)
        self.assertEqual(['A', 'B'], [s.name for s in voc.sections])

        section_session = self.db.create_new_session(self.user, voc,
                                                     section='B')
        self.assertTrue(section_session.is_flipped)
        self.assertEqual(1, len(section_session.vocabulary))

        attempt = section_session.guess(section_session.current_word,
                                        section_session.current_word.word_output)
        self.db.add_word_attempt(section_session, attempt)

        reloaded = self.db.load_session(section_session.id)
        self.assertTrue(reloaded.is_flipped)
        self.assertEqual(1, len(reloaded.vocabulary))
        self.assertEqual(1, len(reloaded.attempts))
        self.assertTrue(reloaded.is_finished)

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

        self.db.add_word_attempt(session_fetched, attempt)

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
        self.db.add_word_attempt(session, word_attempt)

        self.assertTrue(word_attempt.success)
        self.db.last_session(self.user, new_voc)

    def test_load_dictionary(self):
        import tempfile
        import os
        from cli import load_dictionary

        fd, path = tempfile.mkstemp(suffix='.csv')
        os.close(fd)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write('vocabulary;section;german;translation\n')
                f.write('1 Beschreibung von Menschen;;sein*;être\n')
                f.write('1 Beschreibung von Menschen;;haben;avoir\n')
                f.write('2 Kleidung und Mode;Verbs;tragen;porter\n')
                f.write('2 Kleidung und Mode;Verbs;anziehen;to put on\n')

            vocabularies = load_dictionary(path)

            self.assertEqual(2, len(vocabularies))

            voc1 = vocabularies[0]
            self.assertEqual('fr', voc1.input_language)
            self.assertEqual('de', voc1.output_language)
            self.assertEqual('1 Beschreibung von Menschen',
                             voc1.name.word_input)
            self.assertEqual([], [s.name for s in voc1.sections])
            self.assertEqual(2, len(voc1.words))
            self.assertEqual('sein*', voc1.words[0].word_output)
            self.assertEqual('être', voc1.words[0].word_input)
            self.assertIsNone(voc1.section_of(voc1.words[0]))

            voc2 = vocabularies[1]
            self.assertEqual('fr', voc2.input_language)
            self.assertEqual('2 Kleidung und Mode',
                             voc2.name.word_input)
            self.assertEqual(['Verbs'], [s.name for s in voc2.sections])
            self.assertEqual(2, len(voc2.words))
            self.assertEqual('Verbs', voc2.section_of(voc2.words[0]))
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_known_word_counts_by_user(self):
        self._create_vocabulary()
        self._create_user()

        other = self.db.create_user('other@x.com', 'abc',
                                    {Language.FRENCH})

        def practice(user):
            session = self.db.create_new_session(user, self.new_voc)
            word = session.current_word
            attempt = session.guess(word, word.word_output)
            self.db.add_word_attempt(session, attempt)

        practice(self.user)
        practice(other)

        users = self.db.list_users()
        self.assertEqual(2, len(users))
        user_ids = {email: user_id for user_id, email in users}
        self.assertEqual({'test@hotmail.com', 'other@x.com'},
                         set(user_ids))

        counts = self.db.known_word_counts_by_user()
        self.assertEqual(1, sum(counts[user_ids['test@hotmail.com']].values()))
        self.assertEqual(1, sum(counts[user_ids['other@x.com']].values()))

    def test_migration_adds_section_columns(self):
        import os
        import tempfile

        import store as store_module

        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        try:
            raw = store_module.SqliteDatabase(path)
            raw.execute_sql(
                'CREATE TABLE dbword (id INTEGER PRIMARY KEY AUTOINCREMENT, '
                'vocabulary_id INTEGER NOT NULL, word_input VARCHAR(255) NOT NULL, '
                'word_output VARCHAR(255) NOT NULL, directive VARCHAR(255))')
            raw.execute_sql(
                'CREATE TABLE dbvocabularysession (id INTEGER PRIMARY KEY AUTOINCREMENT, '
                'session_id INTEGER NOT NULL, vocabulary_id INTEGER NOT NULL, '
                'flipped INTEGER NOT NULL)')
            raw.close()

            load_database(path)

            for table in ('dbword', 'dbvocabularysession'):
                cursor = store_module.db.execute_sql(
                    'PRAGMA table_info(%s)' % table)
                columns = [row[1] for row in cursor.fetchall()]
                self.assertIn('section', columns)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_remove_vocabulary(self):
        self._create_vocabulary()
        self._create_user()

        self.db.create_new_session(self.user, self.new_voc)
        session = self.db.last_session(self.user, self.new_voc)
        session.guess(self.word1, self.word1.word_output)

        self.db.remove_vocabulary(self.new_voc)

        self.assertEqual({}, self.db.list_vocabularies(None))

    def test_add_word(self):
        self._create_vocabulary()
        self._create_user()

        self.word3 = Word(word_input='fr_3',
                          word_output='de_3',
                          directive=None)

        self.db.add_word(self.new_voc, self.word3)

        self.db.update_word(self.new_voc, self.word3,
                            word_input='fr_4',
                            word_output='de_4',
                            directive='#name')

        vocs = self.db.list_vocabularies(None)
        new_word = Word(word_input='fr_4',
                        word_output='de_4',
                        directive='#name')

        self.assertIn(new_word, vocs[self.new_voc.id].words)

    def test_save_same_words_twice(self):
        self._create_vocabulary()
        self._create_user()

        session_id = self.db.create_new_session(self.user, self.new_voc)
        self.assertIsNotNone(session_id)

        session = self.db.last_session(self.user, self.new_voc)
        self.assertEqual(session_id.id, session.id)

        first_word = session.current_word

        word_attempt = session.guess(session.current_word,
                                     session.current_word.word_output)

        self.db.add_word_attempt(session, word_attempt)
        self.db.add_word_attempt(session, word_attempt)

        session2 = self.db.last_session(self.user, self.new_voc)

        self.assertEqual(2, len(session2.attempts))


if __name__ == '__main__':
    unittest.main(verbosity=3)

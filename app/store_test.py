# -*- coding: utf-8 -*-

import os
import sqlite3
import tempfile
import unittest

from typing import Set

from store import (load_database, DbException,
                   DbVocabulary, DbVocabularyTitle, DbSection, DbSectionText,
                   DbWord, DbWordText, DbVocabularySession, DbWordAttempt,
                   DbUser)
from learn import Vocabulary, Word, Language, User


class TestStore(unittest.TestCase):

    def setUp(self):
        self.db = load_database(':memory:')

        for language in Language:
            self.db.create_language(language)

    def _create_vocabulary(self):

        self.word1 = Word(word_input='fr_1',
                          word_output='de_1')
        self.word2 = Word(word_input='fr_2',
                          word_output='de_2')
        self.words = [self.word1, self.word2]

        self.new_voc = Vocabulary(self.word1, self.words,
                                  input_language='fr',
                                  output_language='de')

        voc_id = self.db.create_vocabulary(self.new_voc)
        self.assertEqual(1, voc_id)

    def _create_user(self, main_language: Language = None):
        if main_language is None:
            main_language = Language.FRENCH
        self.user = self.db.create_user('test@hotmail.com', 'abc',
                                        main_language)

    def _projection(self, voc_id: int = 1,
                    target: Language = Language.GERMAN) -> Vocabulary:
        return self.db.get_vocabulary(self.user, voc_id, target)

    def test_voc(self):
        self._create_vocabulary()
        self._create_user()

        vocs = self.db.list_vocabularies(self.user, Language.GERMAN)
        self.assertEqual(1, len(vocs))

        voc = next(iter(vocs.values()))
        self.assertEqual([self.word1, self.word2], voc.words)
        self.assertEqual('fr', voc.input_language)
        self.assertEqual('de', voc.output_language)
        self.assertEqual('fr_1', voc.name.word_input)

    def test_language_agnostic_entities(self):
        self._create_vocabulary()

        self.assertEqual(1, DbVocabulary.select().count())
        self.assertEqual(2, DbWord.select().count())
        self.assertEqual(4, DbWordText.select().count())
        self.assertEqual(2, DbVocabularyTitle.select().count())

    def test_manage_sessions(self):
        self._create_vocabulary()
        self._create_user()

        voc = self._projection()
        self.assertIsNone(self.db.last_session(self.user, voc))

        created = self.db.create_new_session(self.user, voc)
        self.assertIsNotNone(created.id)

        session = self.db.last_session(self.user, voc)
        self.assertEqual(created.id, session.id)

        first_word = session.current_word

        self.assertTrue((self.word1 == session.current_word) or
                        (self.word2 == session.current_word))

        word_attempt = session.guess(session.current_word,
                                     session.current_word.word_output)
        self.db.add_word_attempt(session, word_attempt)

        db_session = self.db.load_session(session.id)
        self.assertNotEqual(first_word, db_session.current_word)
        self.assertFalse(db_session.is_finished)

        self.assertIsNone(self.db.last_session(self.user, voc,
                                               finished=True))
        self.assertIsNotNone(self.db.last_session(self.user, voc,
                                                  finished=False))

        word_attempt = session.guess(session.current_word,
                                     session.current_word.word_output)
        self.db.add_word_attempt(session, word_attempt)

        db_session = self.db.load_session(session.id)
        self.assertTrue(db_session.is_finished)
        self.assertEqual(100.0, db_session.accuracy)

    def test_vocabulary_stats(self):
        self._create_vocabulary()
        self._create_user()

        voc = self._projection()
        new_session = self.db.create_new_session(self.user, voc)

        word = new_session.current_word
        attempt = new_session.guess(word, 'bla')
        self.db.add_word_attempt(new_session, attempt)

        stats = self.db.vocabulary_stats(voc)

        self.assertEqual(100.0, stats.errors_prob_for(word))

    def test_target_languages(self):
        self._create_vocabulary()
        self._create_user()

        targets = self.db.target_languages('fr')
        self.assertEqual([Language.GERMAN], targets)
        self.assertEqual([Language.FRENCH], self.db.target_languages('de'))

    def test_user(self):
        self._create_user()
        self.assertIsNotNone(self.user)
        self.assertEqual(Language.FRENCH, self.user.main_language)

        with self.assertRaises(DbException):
            self.db.create_user('test@hotmail.com', 'other',
                                Language.FRENCH)

        with self.assertRaises(DbException):
            self.db.get_user('test2@gmail.com', 'def')

        other_user = self.db.get_user('test@hotmail.com', 'abc')
        self.assertEqual('test@hotmail.com', other_user.email)

    def _create_sectioned_vocabulary(self):
        self.sec_words = [Word(word_input='fr_1', word_output='de_1'),
                          Word(word_input='fr_2', word_output='de_2'),
                          Word(word_input='fr_3', word_output='de_3')]

        self.sec_voc = Vocabulary(self.sec_words[0], self.sec_words,
                                  input_language='fr',
                                  output_language='de',
                                  sections=['A', 'A', 'B'])

        return self.db.create_vocabulary(self.sec_voc)

    def test_section_persistence(self):
        voc_id = self._create_sectioned_vocabulary()
        self._create_user()

        voc = self._projection(voc_id)

        self.assertEqual(['A', 'B'], [s.name for s in voc.sections])
        self.assertEqual('A', voc.section_of(voc.words[0]))
        self.assertEqual('B', voc.section_of(voc.words[2]))

    def test_section_session(self):
        voc_id = self._create_sectioned_vocabulary()
        self._create_user()

        voc = self._projection(voc_id)

        with self.assertRaises(DbException):
            self.db.create_new_session(self.user, voc, section='Nope')

        whole_session = self.db.create_new_session(self.user, voc)
        section_session = self.db.create_new_session(self.user, voc,
                                                     section='A')

        self.assertEqual(3, len(whole_session.vocabulary))
        self.assertEqual(2, len(section_session.vocabulary))
        self.assertEqual(['A', 'A'],
                         [voc.section_of(w)
                          for w in section_session.vocabulary.words])

        self.assertEqual(whole_session.id,
                         self.db.last_session(self.user, voc,
                                              section='').id)
        self.assertEqual(section_session.id,
                         self.db.last_session(self.user, voc,
                                              section='A').id)

        attempt = section_session.guess(section_session.current_word,
                                        section_session.current_word.word_output)
        self.db.add_word_attempt(section_session, attempt)

        reloaded = self.db.load_session(section_session.id)
        self.assertEqual(2, len(reloaded.vocabulary))
        self.assertEqual(1, len(reloaded.attempts))
        self.assertFalse(reloaded.is_finished)

    def test_known_word_counts_by_user(self):
        self._create_vocabulary()
        self._create_user()

        other = self.db.create_user('other@x.com', 'abc', Language.FRENCH)

        def practice(user):
            voc = self.db.get_vocabulary(user, 1, Language.GERMAN)
            session = self.db.create_new_session(user, voc)
            word = session.current_word
            attempt = session.guess(word, word.word_output)
            self.db.add_word_attempt(session, attempt)

        practice(self.user)
        practice(other)

        users = self.db.list_users()
        self.assertEqual(2, len(users))
        user_ids = {email: user_id for user_id, email in users}

        counts = self.db.known_word_counts_by_user()
        self.assertEqual(1, sum(counts[user_ids['test@hotmail.com']].values()))
        self.assertEqual(1, sum(counts[user_ids['other@x.com']].values()))

    def test_load_dictionary(self):
        from cli import load_dictionary

        fd, path = tempfile.mkstemp(suffix='.csv')
        os.close(fd)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write('vocabulary;section;german;translation\n')
                f.write('1 Menschen;;sein*;être\n')
                f.write('1 Menschen;;haben;avoir\n')
                f.write('2 Mode;Verbs;tragen;porter\n')
                f.write('2 Mode;Verbs;anziehen;to put on\n')

            vocabularies = load_dictionary(path)
            self.assertEqual(2, len(vocabularies))

            voc1 = vocabularies[0]
            self.assertEqual('fr', voc1.input_language)
            self.assertEqual('de', voc1.output_language)
            self.assertEqual('1 Menschen', voc1.name.word_input)
            self.assertEqual(2, len(voc1.words))
            self.assertIsNone(voc1.section_of(voc1.words[0]))

            voc_id = self.db.create_vocabulary(voc1)
            self._create_user()
            projection = self._projection(voc_id)
            self.assertEqual(2, len(projection.words))
            self.assertEqual('sein*', projection.words[0].word_output)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_add_word_and_update_text(self):
        self._create_vocabulary()
        self._create_user()

        word = Word(word_input='fr_3', word_output='de_3')
        word_id = self.db.add_word(1, 'fr', 'de', word)

        self.db.update_word_text(word_id, 'de', text='de_4',
                                 example='ein Beispiel')

        texts = self.db.list_word_texts(1)
        self.assertEqual('de_4', texts[word_id]['de']['text'])
        self.assertEqual('ein Beispiel', texts[word_id]['de']['example'])
        self.assertEqual('fr_3', texts[word_id]['fr']['text'])

    def test_remove_vocabulary(self):
        self._create_vocabulary()
        self._create_user()

        voc = self._projection()
        self.db.create_new_session(self.user, voc)

        self.db.remove_vocabulary(1)

        self.assertEqual({}, self.db.list_vocabularies(self.user,
                                                       Language.GERMAN))
        self.assertEqual(0, DbWord.select().count())
        self.assertEqual(0, DbWordText.select().count())

    def test_legacy_migration(self):
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        try:
            con = sqlite3.connect(path)
            con.executescript(
                "CREATE TABLE dblanguage (code VARCHAR(255) PRIMARY KEY, "
                "name VARCHAR(255) NOT NULL);"
                "CREATE TABLE dbuser (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "email VARCHAR(255) NOT NULL, password VARCHAR(255) NOT NULL);"
                "CREATE TABLE dbspeak (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "language_id VARCHAR(255) NOT NULL, user_id INTEGER NOT NULL);"
                "CREATE TABLE dbvocabulary (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "input_language_id VARCHAR(255) NOT NULL, "
                "output_language_id VARCHAR(255) NOT NULL, name VARCHAR(255));"
                "CREATE TABLE dbword (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "vocabulary_id INTEGER NOT NULL, word_input VARCHAR(255) NOT NULL, "
                "word_output VARCHAR(255) NOT NULL, section VARCHAR(255));"
                "CREATE TABLE dbsession (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "user_id INTEGER NOT NULL, current_word_id INTEGER, "
                "creation DATETIME NOT NULL, finished SMALLINT NOT NULL);"
                "CREATE TABLE dbvocabularysession (id INTEGER PRIMARY KEY "
                "AUTOINCREMENT, session_id INTEGER NOT NULL, "
                "vocabulary_id INTEGER NOT NULL, flipped SMALLINT NOT NULL, "
                "section VARCHAR(255));"
                "CREATE TABLE dbwordattempt (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "word_id INTEGER NOT NULL, session_id INTEGER NOT NULL, "
                "typed_word VARCHAR(255) NOT NULL, success SMALLINT NOT NULL, "
                "time DATETIME NOT NULL);"
                "INSERT INTO dblanguage VALUES ('fr','French'),('de','German');"
                "INSERT INTO dbuser (id,email,password) VALUES (1,'u@x','pw');"
                "INSERT INTO dbspeak (language_id,user_id) VALUES ('fr',1);"
                "INSERT INTO dbvocabulary "
                "(id,input_language_id,output_language_id,name) "
                "VALUES (1,'fr','de','Test');"
                "INSERT INTO dbword "
                "(id,vocabulary_id,word_input,word_output,section) "
                "VALUES (1,1,'un','eins','A'),(2,1,'deux','zwei',NULL);"
                "INSERT INTO dbsession (id,user_id,creation,finished) "
                "VALUES (1,1,'2020-01-01',0);"
                "INSERT INTO dbvocabularysession "
                "(id,session_id,vocabulary_id,flipped,section) "
                "VALUES (1,1,1,0,'A');"
                "INSERT INTO dbwordattempt "
                "(id,word_id,session_id,typed_word,success,time) "
                "VALUES (1,1,1,'eins',1,'2020-01-01');"
            )
            con.commit()
            con.close()

            database = load_database(path)

            self.assertEqual(1, DbVocabulary.select().count())
            self.assertEqual(2, DbWord.select().count())
            self.assertEqual(4, DbWordText.select().count())
            self.assertEqual(1, DbSection.select().count())
            self.assertEqual(1, DbWordAttempt.select().count())

            db_user = DbUser.get(DbUser.id == 1)
            self.assertEqual('fr', db_user.main_language_id)

            user = User(email='u@x', password='pw',
                        main_language=Language.FRENCH)
            vocs = database.list_vocabularies(user, Language.GERMAN)
            self.assertEqual(1, len(vocs))

            voc = next(iter(vocs.values()))
            self.assertEqual('Test', voc.name.word_input)
            self.assertEqual(2, len(voc.words))
            self.assertEqual(['A'], [s.name for s in voc.sections])

            session = database.load_session(1)
            self.assertEqual(1, len(session.attempts))
            self.assertEqual('eins', session.attempts[0].word.word_output)
        finally:
            if os.path.exists(path):
                os.remove(path)


if __name__ == '__main__':
    unittest.main(verbosity=3)

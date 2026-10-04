# -*- coding: utf-8 -*-

import os
import sqlite3
import tempfile
import unittest

from typing import Set

from store import (load_database, DbException,
                   DbVocabulary, DbVocabularyTitle, DbSection, DbSectionText,
                   DbWord, DbWordText, DbVocabularySession, DbWordAttempt,
                   DbUser, DbSession, db as store_db, _table_columns)
from learn import Vocabulary, Word, Language, User, included_levels
from optimizer import AiStrategy, FullStrategy


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

        stats = self.db.vocabulary_stats(voc, self.user)

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
            while not session.is_finished:
                word = session.current_word
                attempt = session.guess(word, word.word_output)
                self.db.add_word_attempt(session, attempt)

        practice(self.user)
        practice(other)

        users = self.db.list_users()
        self.assertEqual(2, len(users))
        user_ids = {email: user_id for user_id, email in users}

        counts = self.db.known_word_counts_by_user()
        self.assertEqual(2, sum(counts[user_ids['test@hotmail.com']].values()))
        self.assertEqual(2, sum(counts[user_ids['other@x.com']].values()))

    def test_unknown_after_abandoned_session(self):
        # a right guess in a run which was never completed does not mark
        # the word as known: only completed runs count
        self._create_vocabulary()
        self._create_user()

        voc = self._projection()
        session = self.db.create_new_session(self.user, voc)

        word = session.current_word
        attempt = session.guess(word, word.word_output)
        self.db.add_word_attempt(session, attempt)

        # the run is abandoned: the word is not known yet
        self.assertFalse(session.is_finished)
        self.assertEqual(
            0, self.db.known_word_counts(self.user).get(voc.id, 0))

        # finish the run -> the practised words become known
        while not session.is_finished:
            word = session.current_word
            attempt = session.guess(word, word.word_output)
            self.db.add_word_attempt(session, attempt)

        self.assertEqual(
            2, self.db.known_word_counts(self.user).get(voc.id, 0))

    def test_known_word_counts_are_scoped_to_the_user(self):
        # two users practising the same vocabulary must each see only the
        # words they mastered (no leaking from other users)
        self._create_vocabulary()
        self._create_user()

        other = self.db.create_user('other@x.com', 'abc', Language.FRENCH)
        voc = self._projection()

        def finish(user):
            session = self.db.create_new_session(user, voc)
            while not session.is_finished:
                word = session.current_word
                attempt = session.guess(word, word.word_output)
                self.db.add_word_attempt(session, attempt)

        # our user completes the whole run; the other one abandons after
        # a single correct answer
        finish(self.user)
        abandoned = self.db.create_new_session(other, voc)
        attempt = abandoned.guess(abandoned.current_word,
                                  abandoned.current_word.word_output)
        self.db.add_word_attempt(abandoned, attempt)

        self.assertEqual(2, self.db.known_word_counts(self.user).get(voc.id))
        self.assertEqual(0, self.db.known_word_counts(other).get(voc.id, 0))

    def test_vocabulary_stats_are_scoped_to_the_user(self):
        # the error rate of a word must not include other users' attempts
        self._create_vocabulary()
        self._create_user()

        other = self.db.create_user('other@x.com', 'abc', Language.FRENCH)
        voc = self._projection()

        def fail(user):
            session = self.db.create_new_session(user, voc)
            word = session.current_word
            attempt = session.guess(word, 'wrong-answer')
            self.db.add_word_attempt(session, attempt)
            return word

        word = fail(other)   # another user gets this word wrong twice
        fail(other)

        # our user has no attempts at all -> no error for this word
        stats = self.db.vocabulary_stats(voc, self.user)
        self.assertEqual(0.0, stats.errors_prob_for(word))

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

    def test_user_strategy(self):
        # the default strategy is 'full' (historical behaviour)
        self._create_vocabulary()
        self._create_user()
        self.assertEqual('full', self.user.strategy)

        # a new session follows the user's strategy
        voc = self._projection()
        default_session = self.db.create_new_session(self.user, voc)
        self.assertIsInstance(default_session.strategy, FullStrategy)

        # switching to the AI strategy applies to the next sessions
        self.db.set_user_strategy(self.user, 'ai')
        refreshed = self.db.get_user('test@hotmail.com', 'abc')
        self.assertEqual('ai', refreshed.strategy)

        ai_session = self.db.create_new_session(refreshed, voc)
        self.assertIsInstance(ai_session.strategy, AiStrategy)

        # resuming a session keeps the strategy of its owner
        word = ai_session.current_word
        self.db.add_word_attempt(
            ai_session, ai_session.guess(word, word.word_output))
        reloaded = self.db.load_session(ai_session.id)
        self.assertIsInstance(reloaded.strategy, AiStrategy)

    def test_user_level(self):
        self._create_user()
        self.assertIsNone(self.user.level)

        self.db.set_user_level(self.user, 'B2')
        self.assertEqual('B2', self.db.get_user('test@hotmail.com',
                                                'abc').level)

        # also accepts an email
        self.db.set_user_level('test@hotmail.com', 'C1')
        self.assertEqual('C1', self.db.get_user('test@hotmail.com',
                                                'abc').level)

        with self.assertRaises(DbException):
            self.db.set_user_level('nobody@x.com', 'B1')

    def test_level_filtering(self):
        words = [Word(word_input='fr_b1', word_output='de_b1', level='B1'),
                 Word(word_input='fr_b2', word_output='de_b2', level='B2'),
                 Word(word_input='fr_c1', word_output='de_c1', level='C1'),
                 # no level -> always included
                 Word(word_input='fr_uk', word_output='de_uk')]
        voc = Vocabulary(None, words,
                         input_language='fr', output_language='de')
        voc_id = self.db.create_vocabulary(voc)
        self._create_user()

        def outputs(level):
            projection = self.db.get_vocabulary(
                self.user, voc_id, Language.GERMAN,
                levels=included_levels(level))
            return sorted(w.word_output for w in projection.words)

        self.assertEqual(['de_b1', 'de_uk'], outputs('B1'))
        self.assertEqual(['de_b1', 'de_b2', 'de_uk'], outputs('B2'))
        self.assertEqual(['de_b1', 'de_b2', 'de_c1', 'de_uk'], outputs('C1'))
        self.assertEqual(4, len(outputs(None)))

        # vocabularies without words at the level are not listed
        listed = self.db.list_vocabularies(self.user, Language.GERMAN,
                                           levels=included_levels('B1'))
        self.assertEqual([voc_id], list(listed.keys()))

    def test_session_keeps_level(self):
        words = [Word(word_input='fr_b1', word_output='de_b1', level='B1'),
                 Word(word_input='fr_b2', word_output='de_b2', level='B2'),
                 Word(word_input='fr_c1', word_output='de_c1', level='C1')]
        voc = Vocabulary(None, words,
                         input_language='fr', output_language='de')
        voc_id = self.db.create_vocabulary(voc)
        self._create_user()

        projection = self.db.get_vocabulary(self.user, voc_id,
                                            Language.GERMAN,
                                            levels=included_levels('B2'))
        self.assertEqual(2, len(projection))

        session = self.db.create_new_session(self.user, projection,
                                             level='B2')
        self.assertEqual(2, len(session.vocabulary))

        # even after the user changes level, the session keeps its set
        self.db.set_user_level(self.user, 'C1')
        reloaded = self.db.load_session(session.id)
        self.assertEqual(2, len(reloaded.vocabulary))

    def test_known_word_counts_by_level(self):
        words = [Word(word_input='fr_b1', word_output='de_b1', level='B1'),
                 Word(word_input='fr_b2', word_output='de_b2', level='B2')]
        voc = Vocabulary(None, words,
                         input_language='fr', output_language='de')
        voc_id = self.db.create_vocabulary(voc)
        self._create_user()

        projection = self.db.get_vocabulary(self.user, voc_id,
                                            Language.GERMAN)
        session = self.db.create_new_session(self.user, projection)
        while not session.is_finished:
            word = session.current_word
            attempt = session.guess(word, word.word_output)
            self.db.add_word_attempt(session, attempt)

        self.assertEqual(2, self.db.known_word_counts(self.user).get(voc_id))
        self.assertEqual(1, self.db.known_word_counts(
            self.user, included_levels('B1')).get(voc_id))

    def test_update_and_list_users(self):
        self._create_user()

        details = self.db.list_user_details()
        self.assertEqual(1, len(details))
        self.assertEqual('test@hotmail.com', details[0]['email'])
        self.assertEqual('fr', details[0]['main_language'])
        self.assertIsNone(details[0]['level'])
        self.assertIsNone(details[0]['target_language'])

        self.db.update_user('test@hotmail.com', level='B2',
                            main_language=Language.GERMAN,
                            target_language=Language.FRENCH)
        updated = self.db.get_user('test@hotmail.com', 'abc')
        self.assertEqual('B2', updated.level)
        self.assertEqual(Language.GERMAN, updated.main_language)
        self.assertEqual(Language.FRENCH, updated.target_language)
        self.assertEqual('fr',
                         self.db.list_user_details()[0]['target_language'])

        # the shortcut updates the cache too
        self.db.set_user_target_language('test@hotmail.com', 'en')
        self.assertEqual(Language.ENGLISH,
                         self.db.get_user('test@hotmail.com',
                                          'abc').target_language)

        self.db.update_user('test@hotmail.com', password='newpass')
        with self.assertRaises(DbException):
            self.db.get_user('test@hotmail.com', 'abc')
        self.assertEqual('test@hotmail.com',
                         self.db.get_user('test@hotmail.com',
                                          'newpass').email)

        with self.assertRaises(DbException):
            self.db.update_user('nobody@x.com', level='B1')

    def test_a2_level_is_remapped_to_b1(self):
        from store import _remap_old_levels

        word = Word(word_input='fr_1', word_output='de_1', level='A2')
        self.db.create_vocabulary(Vocabulary(None, [word], 'fr', 'de'))
        self.db.create_user('a2@x.com', 'abc', Language.FRENCH, level='A2')

        _remap_old_levels()

        self.assertEqual('B1', DbWord.get().level)
        self.assertEqual('B1', DbUser.get(DbUser.email == 'a2@x.com').level)

    def test_remove_user(self):
        self._create_vocabulary()
        self._create_user()

        voc = self._projection()
        session = self.db.create_new_session(self.user, voc)
        word = session.current_word
        self.db.add_word_attempt(session,
                                 session.guess(word, word.word_output))

        self.assertEqual(1, DbSession.select().count())
        self.assertEqual(1, DbWordAttempt.select().count())

        self.db.remove_user('test@hotmail.com')

        self.assertEqual(0, DbUser.select().count())
        self.assertEqual(0, DbSession.select().count())
        self.assertEqual(0, DbVocabularySession.select().count())
        self.assertEqual(0, DbWordAttempt.select().count())
        # vocabularies are not touched
        self.assertEqual(1, DbVocabulary.select().count())
        self.assertEqual(2, DbWord.select().count())

        with self.assertRaises(DbException):
            self.db.get_user('test@hotmail.com', 'abc')
        with self.assertRaises(DbException):
            self.db.remove_user('nobody@x.com')

    def test_import_vocabularies_update(self):
        self.db.import_vocabularies([
            {'id': 10, 'vocabulary': 'Greetings', 'section': '',
             'type': 'noun', 'level': 'B1',
             'texts': {'de': 'Hallo', 'fr': 'bonjour'}, 'examples': {}}])

        self.assertEqual(10, DbWord.get().id)

        self._create_user()   # main language: french
        voc = self.db.get_vocabulary(self.user, 1, Language.GERMAN)
        session = self.db.create_new_session(self.user, voc)
        word = session.current_word
        self.db.add_word_attempt(session,
                                 session.guess(word, word.word_output))
        self.assertEqual(1, DbWordAttempt.select().count())

        # re-import without replacing: the word ids are stable, the texts
        # are updated, new words are added and the history survives
        self.db.import_vocabularies([
            {'id': 10, 'vocabulary': 'Greetings', 'section': '',
             'type': 'noun', 'level': 'B2',
             'texts': {'de': 'Hallo', 'fr': 'salut', 'en': 'hello'},
             'examples': {'de': 'Hallo Welt.'}},
            {'id': 11, 'vocabulary': 'Greetings', 'section': '',
             'type': 'verb', 'level': 'B1',
             'texts': {'de': 'gehen', 'fr': 'aller'}, 'examples': {}},
        ], replace=False)

        self.assertEqual(1, DbVocabulary.select().count())
        self.assertEqual(2, DbWord.select().count())
        self.assertEqual(1, DbWordAttempt.select().count())
        self.assertEqual(1, DbSession.select().count())

        self.assertEqual('B2', DbWord.get(DbWord.id == 10).level)
        texts = {t.language_id: t.text for t in
                 DbWordText.select().where(DbWordText.word == 10)}
        self.assertEqual('salut', texts['fr'])
        self.assertEqual('hello', texts['en'])
        example = DbWordText.get((DbWordText.word == 10) &
                                 (DbWordText.language == 'de')).example
        self.assertEqual('Hallo Welt.', example)

    def test_import_changes(self):
        # the --update preview lists every change but leaves out the
        # words which would not change, and modifies nothing
        self.db.import_vocabularies([
            {'id': 10, 'vocabulary': 'Greetings', 'section': 'Basics',
             'type': 'noun', 'level': 'B1',
             'texts': {'de': 'Hallo', 'fr': 'bonjour'},
             'examples': {'de': 'Hallo Welt.'}},
            {'id': 11, 'vocabulary': 'Greetings', 'section': 'Basics',
             'type': 'verb', 'level': 'B2',
             'texts': {'de': 'gehen', 'fr': 'aller'}, 'examples': {}},
        ])

        changes = self.db.import_changes([
            # 10 is unchanged: it must not appear in the preview
            {'id': 10, 'vocabulary': 'Greetings', 'section': 'Basics',
             'type': 'noun', 'level': 'B1',
             'texts': {'de': 'Hallo', 'fr': 'bonjour'},
             'examples': {'de': 'Hallo Welt.'}},
            # level and translation change
            {'id': 11, 'vocabulary': 'Greetings', 'section': 'Basics',
             'type': 'verb', 'level': 'B1',
             'texts': {'de': 'gehen', 'fr': 'aller maintenant'},
             'examples': {}},
            # a brand new word
            {'id': 12, 'vocabulary': 'Greetings', 'section': 'Basics',
             'type': 'noun', 'level': 'C1',
             'texts': {'de': 'wiedersehen', 'fr': 'revoir'}, 'examples': {}},
            # a new section inside the existing vocabulary
            {'id': 13, 'vocabulary': 'Greetings', 'section': 'Travel',
             'type': 'noun', 'level': 'B1',
             'texts': {'de': 'Zug', 'fr': 'train'}, 'examples': {}},
            # a brand new vocabulary with a new word
            {'id': 14, 'vocabulary': 'Colors', 'section': '',
             'type': 'adjective', 'level': 'B1',
             'texts': {'de': 'rot', 'fr': 'rouge'}, 'examples': {}},
        ])

        joined = '\n'.join(changes)
        self.assertNotIn('word 10', joined)
        self.assertIn('word 11 (gehen):', joined)
        self.assertIn('level B2 -> B1', joined)
        self.assertIn('fr text "aller" -> "aller maintenant"', joined)
        self.assertIn('add word 12: de "wiedersehen", fr "revoir"', joined)
        self.assertIn('add section "Travel" (Greetings)', joined)
        self.assertIn('add vocabulary "Colors"', joined)

        # the preview must not modify the database
        self.assertEqual(1, DbVocabulary.select().count())
        self.assertEqual(2, DbWord.select().count())
        self.assertEqual('B2', DbWord.get(DbWord.id == 11).level)

    def test_input_example(self):
        # examples in the learner's own language (the input language of
        # the session) are kept per word and surface on the attempts
        self.db.import_vocabularies([
            {'id': 10, 'vocabulary': 'Greetings', 'section': '',
             'type': 'noun', 'level': 'B1',
             'texts': {'de': 'Hallo', 'fr': 'bonjour'},
             'examples': {'de': 'Hallo Welt.', 'fr': 'Bonjour le monde.'}},
        ])
        self._create_user()   # main language: french

        voc = self.db.get_vocabulary(self.user, 1, Language.GERMAN)
        word = voc.words[0]
        self.assertEqual('Hallo Welt.', voc.example(word))
        self.assertEqual('Bonjour le monde.', voc.input_example(word))

        # a session captures both examples on each attempt
        session = self.db.create_new_session(self.user, voc)
        attempt = session.guess(word, word.word_output)
        self.db.add_word_attempt(session, attempt)
        self.assertEqual('Hallo Welt.', attempt.example)
        self.assertEqual('Bonjour le monde.', attempt.input_example)

        # and reloading the session recomputes them
        reloaded = self.db.load_session(session.id)
        self.assertEqual('Bonjour le monde.',
                         reloaded.attempts[-1].input_example)

        # a section keeps the input examples too
        self.db.import_vocabularies([
            {'id': 11, 'vocabulary': 'Greetings', 'section': 'Basics',
             'type': 'noun', 'level': 'B1',
             'texts': {'de': 'gehen', 'fr': 'aller'},
             'examples': {'de': 'Ich gehe.', 'fr': "J'y vais."}},
        ], replace=False)
        sectioned = db_voc = self.db.get_vocabulary(self.user, 1,
                                                    Language.GERMAN)
        sect = sectioned.section('Basics')
        self.assertEqual("J'y vais.",
                         sect.input_example(sect.words[0]))

    def test_attempt_keeps_its_timestamp(self):
        # the stored timestamp is the moment the word was tried, not the
        # moment the attempt row was saved
        self._create_vocabulary()
        self._create_user()
        voc = self._projection()
        session = self.db.create_new_session(self.user, voc)

        word = session.current_word
        attempt = session.guess(word, word.word_output)
        self.db.add_word_attempt(session, attempt)

        stored = DbWordAttempt.get(DbWordAttempt.session == session.id)
        self.assertEqual(attempt.time, stored.time)

        # the helper returns the same timestamp, most recent first
        rows = self.db.word_attempts(voc.id)
        self.assertEqual(1, len(rows))
        self.assertEqual(stored.time, rows[0][3])

    def test_load_csv_dictionary(self):
        from cli import load_csv_dictionary

        fd, path = tempfile.mkstemp(suffix='.csv')
        os.close(fd)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write('id,vocabulary,section,type,cefr_level,german,'
                        'french,english,german_example\n')
                f.write('7,Greetings,Basics,noun,B1,Hallo,bonjour,hello,'
                        'Hallo Welt.\n')
                f.write('8,Greetings,Basics,verb,B2,gehen,aller,to go,\n')
                f.write('9,Greetings,,,C1,,,,,\n')   # no text -> skipped

            records = load_csv_dictionary(path)

            self.assertEqual(2, len(records))
            self.assertEqual(7, records[0]['id'])
            self.assertEqual(8, records[1]['id'])
            self.assertEqual('Greetings', records[0]['vocabulary'])
            self.assertEqual('Basics', records[0]['section'])
            self.assertEqual('noun', records[0]['type'])
            self.assertEqual('B1', records[0]['level'])
            self.assertEqual({'de': 'Hallo', 'fr': 'bonjour',
                              'en': 'hello'}, records[0]['texts'])
            self.assertEqual({'de': 'Hallo Welt.'},
                             records[0]['examples'])
            self.assertEqual({'de': 'gehen', 'fr': 'aller',
                              'en': 'to go'}, records[1]['texts'])
            self.assertEqual({}, records[1]['examples'])
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_import_vocabularies(self):
        records = [
            {'vocabulary': 'Greetings', 'section': 'Basics', 'type': 'noun',
             'level': 'B1',
             'texts': {'de': 'Hallo', 'fr': 'bonjour', 'en': 'hello'},
             'examples': {'de': 'Hallo Welt.'}},
            {'vocabulary': 'Greetings', 'section': 'Basics', 'type': None,
             'level': 'B2',
             'texts': {'de': 'Tschuess', 'fr': 'au revoir', 'en': 'bye'},
             'examples': {}},
        ]

        count = self.db.import_vocabularies(records)
        self.assertEqual(1, count)
        self.assertEqual(1, DbVocabulary.select().count())
        self.assertEqual(1, DbVocabularyTitle.select().count())
        self.assertEqual(1, DbSection.select().count())
        self.assertEqual(1, DbSectionText.select().count())
        self.assertEqual(2, DbWord.select().count())
        self.assertEqual(6, DbWordText.select().count())

        self._create_user()   # main language: french
        voc = self.db.get_vocabulary(self.user, 1, Language.GERMAN)
        self.assertEqual('Greetings', voc.name.word_input)
        self.assertEqual('Basics', voc.sections[0].name)

        words = {word.word_output: word for word in voc.words}
        self.assertEqual('noun', words['Hallo'].type)
        self.assertEqual('B1', words['Hallo'].level)
        self.assertEqual('bonjour', words['Hallo'].word_input)
        self.assertEqual('Hallo Welt.', voc.example(words['Hallo']))

        # practising, then re-importing replaces everything
        session = self.db.create_new_session(self.user, voc)
        word = session.current_word
        self.db.add_word_attempt(session,
                                 session.guess(word, word.word_output))
        self.assertGreater(DbWordAttempt.select().count(), 0)

        self.db.import_vocabularies([
            {'vocabulary': 'Other', 'section': '', 'type': None,
             'level': 'C1', 'texts': {'de': 'Danke', 'fr': 'merci'},
             'examples': {}}])

        self.assertEqual(1, DbVocabulary.select().count())
        self.assertEqual(1, DbWord.select().count())
        self.assertEqual(0, DbSection.select().count())
        self.assertEqual(0, DbWordAttempt.select().count())
        self.assertEqual(0, DbSession.select().count())

    def test_word_level(self):
        self._create_vocabulary()
        self._create_user()

        word_id = self.db.add_word(
            1, 'fr', 'de',
            Word(word_input='fr_3', word_output='de_3', level='B2'))

        voc = self._projection()
        word = [w for w in voc.words if w.word_output == 'de_3'][0]
        self.assertEqual('B2', word.level)

        self.db.update_word_level(word_id, 'C1')
        voc = self._projection()
        word = [w for w in voc.words if w.word_output == 'de_3'][0]
        self.assertEqual('C1', word.level)

        # the default is None when the level is unknown
        self.assertIsNone(voc.words[0].level)

    def test_level_backfills_b1(self):
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        try:
            database = load_database(path)
            for language in Language:
                database.create_language(language)
            database.create_vocabulary(
                Vocabulary(None,
                           [Word(word_input='fr_1', word_output='de_1')],
                           input_language='fr', output_language='de'))

            # pretend the database predates the 'level' column
            store_db.execute_sql('ALTER TABLE dbword DROP COLUMN level')
            self.assertNotIn('level', _table_columns('dbword'))

            database = load_database(path)

            self.assertEqual('B1', DbWord.get().level)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_word_type(self):
        self._create_vocabulary()
        self._create_user()

        # a word added through the CLI style API carries its type
        word_id = self.db.add_word(
            1, 'fr', 'de',
            Word(word_input='fr_3', word_output='de_3', type='verb'))

        voc = self._projection()
        typed = [w for w in voc.words if w.word_output == 'de_3'][0]
        self.assertEqual('verb', typed.type)

        # ... and it can be changed (or cleared) later
        self.db.update_word_type(word_id, 'noun')
        voc = self._projection()
        typed = [w for w in voc.words if w.word_output == 'de_3'][0]
        self.assertEqual('noun', typed.type)

        # the default is None when the type is unknown
        self.assertIsNone(voc.words[0].type)

    def test_create_vocabulary_keeps_type(self):
        voc = Vocabulary(None,
                         [Word(word_input='fr_1', word_output='de_1',
                               type='adjective')],
                         input_language='fr', output_language='de')
        self.db.create_vocabulary(voc)
        self._create_user()

        projection = self._projection()
        self.assertEqual('adjective', projection.words[0].type)

    def test_long_example(self):
        self._create_vocabulary()
        self._create_user()

        word_id = self.db.add_word(
            1, 'fr', 'de',
            Word(word_input='fr_9', word_output='de_9'))

        example = 'a' * 1024
        self.db.update_word_text(word_id, 'de', example=example)

        texts = self.db.list_word_texts(1)
        self.assertEqual(1024, len(texts[word_id]['de']['example']))
        self.assertEqual(example, texts[word_id]['de']['example'])

        voc = self._projection()
        word = [w for w in voc.words if w.word_output == 'de_9'][0]
        self.assertEqual(example, voc.example(word))

    def test_attempt_example_on_reload(self):
        voc = Vocabulary(None,
                         [Word(word_input='fr_1', word_output='de_1')],
                         input_language='fr', output_language='de')
        voc.set_example(voc.words[0], 'Ein Beispielsatz.')
        voc_id = self.db.create_vocabulary(voc)
        self._create_user()

        projection = self._projection(voc_id)
        session = self.db.create_new_session(self.user, projection)
        word = session.current_word
        attempt = session.guess(word, word.word_output)
        self.db.add_word_attempt(session, attempt)

        self.assertEqual('Ein Beispielsatz.', attempt.example)

        reloaded = self.db.load_session(session.id)
        self.assertEqual(1, len(reloaded.attempts))
        self.assertEqual('Ein Beispielsatz.', reloaded.attempts[0].example)

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

            # the migration leaves the (unknown) word type as NULL and
            # assumes B1 for the level
            self.assertIsNone(DbWord.get(DbWord.id == 1).type)
            self.assertEqual('B1', DbWord.get(DbWord.id == 1).level)

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

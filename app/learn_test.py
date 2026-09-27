# -*- coding: utf-8 -*-

from io import StringIO
import unittest

from learn import Word, Vocabulary, Session


class LearnTest(unittest.TestCase):

    def setUp(self):
        self.word1 = Word(word_output='word1_output',
                          word_input='word1_input')
        self.word2 = Word(word_output='word2_output',
                          word_input='word2_input')

        words = [self.word1, self.word2]
        self.voc = Vocabulary(self.word1, words, 'fr', 'de')

    def test_learn_vocabulary(self):

        words = Session([], self.voc, self.word1)

        self.assertEqual(self.word1, words.current_word)

        text = 'blabla'
        result = words.guess(words.current_word, text)

        self.assertEqual(text, result.typed_word)
        self.assertEqual(self.word1, result.word)
        self.assertFalse(result.success)

        self.assertEqual(self.word2, words.current_word)

        self.assertEqual(0.0, words.accuracy)
        self.assertFalse(words.is_finished)

        words.guess(words.current_word, self.word2.word_output)
        self.assertEqual(50.0, words.accuracy)
        words.guess(words.current_word, self.word1.word_output)

        self.assertEqual(50.0, words.accuracy)
        self.assertTrue(words.is_finished)

    def test_flip_vocabulary(self):
        new_voc = self.voc.flip()

        self.assertEqual(self.word1.flip(), new_voc.name)

    def test_guess_other_main_word(self):
        """
        A user can guess another word if necessary
        """
        words = Session([], self.voc, self.word1)

        result = words.guess(self.word2, self.word2.word_output)
        self.assertTrue(result.success)

    def test_already_guessed_word(self):
        """
        If a word has already been found, we don't consider the second attempt
        """
        words = Session([], self.voc, self.word1)

        words.guess(self.word1, self.word1.word_output)
        self.assertIsNone(words.guess(self.word1, self.word1.word_output))

    def test_manage_words_with_same_input(self):
        word1 = Word(word_output='word1_output',
                     word_input='word1_input')
        voc1 = Vocabulary(word1, [word1], 'fr', 'de')

        word2 = Word(word_output='word2_output',
                     word_input='word1_input')
        voc2 = Vocabulary(word2, [word2], 'fr', 'de')
        voc1.add(voc2)


        words = Session([], voc1, word1)

        ret = words.guess(word1, word2.word_output)
        self.assertTrue(ret.success)
        self.assertEqual("word2_output", ret.typed_word)
        self.assertEqual(word1, ret.word)

        ret = words.guess(word2, word2.word_output)
        self.assertTrue(ret.success)
        self.assertEqual("word2_output", ret.typed_word)
        self.assertEqual(word2, ret.word)

        self.assertTrue(words.is_finished)

    def test_filter_word(self):
        word = Word(word_output='abc (1)',
                    word_input='def (2)')

        self.assertTrue(word.accepts('abc'))
        self.assertEqual('abc (1)', word.word_output)
        self.assertEqual('def (2)', word.word_input)

        complex_word = Word(word_output='die (other) Umweltverschmutzung (-en) (1)',
                            word_input='def (2)')

        self.assertTrue(complex_word.accepts('die Umweltverschmutzung'))
        self.assertEqual('abc (1)', word.word_output)

    def test_accepts_ignores_plural_and_spaces(self):
        word = Word(word_output='die Beschreibung (-en)',
                    word_input='description')

        self.assertTrue(word.accepts('die Beschreibung', 'de'))
        self.assertTrue(word.accepts('  die Beschreibung  ', 'de'))
        self.assertTrue(word.accepts('Die Beschreibung (-en)', 'de'))
        self.assertFalse(word.accepts('die Erscheinung', 'de'))

    def test_accepts_german_umlauts(self):
        word = Word(word_output='die Größe (-n)',
                    word_input='taille')

        self.assertTrue(word.accepts('die Größe', 'de'))
        self.assertTrue(word.accepts('die Groesse', 'de'))
        self.assertTrue(word.accepts('die groesse', 'de'))

    def test_accepts_french_accents_and_apostrophes(self):
        word = Word(word_output='être',
                    word_input='sein')
        self.assertTrue(word.accepts('etre', 'fr'))
        self.assertTrue(word.accepts('ÊTRE', 'fr'))

        phrase = Word(word_output="avoir l'air",
                      word_input='aussehen')
        self.assertTrue(phrase.accepts('avoir l’air', 'fr'))
        self.assertTrue(phrase.accepts("avoir l' air", 'fr'))
        self.assertTrue(phrase.accepts('avoir lair', 'fr'))
        self.assertFalse(phrase.accepts('avoir', 'fr'))

    def test_add_inherits_languages(self):
        # sessions are rebuilt by merging into an empty vocabulary
        merged = Vocabulary(None, [])
        merged.add(self.voc)

        self.assertEqual('fr', merged.input_language)
        self.assertEqual('de', merged.output_language)

    def test_guess_uses_output_language(self):
        word = Word(word_output='die Beschreibung (-en)',
                    word_input='description')
        vocabulary = Vocabulary(None, [word], 'fr', 'de')
        session = Session([], vocabulary, word)

        attempt = session.guess(word, 'die Beschreibung ')
        self.assertTrue(attempt.success)

    def test_load_vocabulary(self):
        expected_word = Word(word_output='abc',
                             word_input='def')
        voc = Vocabulary.load(StringIO('abc;def'))

        self.assertEqual([expected_word],
                         voc.words)

    def _sectioned_vocabulary(self):
        words = [Word(word_output=f'out_{i}',
                      word_input=f'in_{i}')
                 for i in range(3)]
        return Vocabulary(words[0], words, 'en', 'fr',
                          sections=['A', 'A', 'B'])

    def test_name_is_vocabulary_metadata(self):
        content = ('#input fr\n'
                   '#output de\n'
                   '#name de_example;fr_example\n'
                   'de_a;fr_a\n')
        voc = Vocabulary.load(StringIO(content))

        self.assertIsNotNone(voc.name)
        self.assertEqual('fr_example', voc.name.word_input)
        # the name line is also a regular word
        self.assertEqual(['de_example', 'de_a'],
                         [w.word_output for w in voc.words])

    def test_section_parsing(self):
        content = ('#input en\n'
                   '#output fr\n'
                   '#section A\n'
                   'en_1;fr_1\n'
                   'en_2;fr_2\n'
                   '#section B\n'
                   'en_3;fr_3\n')
        voc = Vocabulary.load(StringIO(content))

        self.assertEqual(['A', 'B'], [s.name for s in voc.sections])
        self.assertEqual(['en_1', 'en_2'],
                         [w.word_output for w in voc.section('A').words])
        self.assertEqual(['en_3'],
                         [w.word_output for w in voc.section('B').words])
        self.assertEqual('A', voc.section_of(voc.words[0]))
        self.assertEqual('B', voc.section_of(voc.words[2]))
        self.assertIsNone(voc.section('Nope'))

    def test_section_keeps_word_ids(self):
        voc = self._sectioned_vocabulary()

        for i, word in enumerate(voc.words):
            voc.set_word_id(word, i + 1)

        section = voc.section('A')

        self.assertEqual(2, len(section.words))
        self.assertEqual({1, 2},
                         {section.word_id(w) for w in section.words})
        self.assertEqual(1, section.word_id(voc.words[0]))

    def test_flip_keeps_sections(self):
        voc = self._sectioned_vocabulary()
        flipped = voc.flip()

        self.assertEqual(['A', 'B'], [s.name for s in flipped.sections])
        self.assertEqual('A', flipped.section_of(flipped.words[0]))
        self.assertEqual(2, len(flipped.section('A').words))

    def test_load_vocabulary_with_language(self):
        expected_word = Word(word_output='abc',
                             word_input='def')
        voc_text = '''
        #input fr
        #output de
        abc;def
        '''

        voc = Vocabulary.load(StringIO(voc_text))
        self.assertEqual([expected_word],
                         voc.words)
        self.assertEqual('fr', voc.input_language)
        self.assertEqual('de', voc.output_language)


if __name__ == '__main__':
    unittest.main(verbosity=3)

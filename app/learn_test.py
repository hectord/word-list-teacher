# -*- coding: utf-8 -*-

import unittest

from learn import Word, Vocabulary, Session


class LearnTest(unittest.TestCase):

    def setUp(self):
        self.word1 = Word(word_output='word1_output',
                          word_input='word1_input',
                          directive='name')
        self.word2 = Word(word_output='word2_output',
                          word_input='word2_input',
                          directive=None)

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
                     word_input='word1_input',
                     directive='name')
        voc1 = Vocabulary(word1, [word1], 'fr', 'de')

        word2 = Word(word_output='word2_output',
                     word_input='word1_input',
                     directive=None)
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
                    word_input='def (2)',
                    directive=None)

        self.assertTrue(word.accepts('abc'))
        self.assertEqual('abc (1)', word.word_output)
        self.assertEqual('def (2)', word.word_input)

        complex_word = Word(word_output='die (other) Umweltverschmutzung (-en) (1)',
                            word_input='def (2)',
                            directive=None)

        self.assertTrue(complex_word.accepts('die Umweltverschmutzung'))
        self.assertEqual('abc (1)', word.word_output)


if __name__ == '__main__':
    unittest.main(verbosity=3)

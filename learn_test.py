# -*- coding: utf-8 -*-

import unittest

from learn import Word, Vocabulary, LearnEngine


class LearnTest(unittest.TestCase):

    def test_learn_vocabulary(self):

        word1 = Word(word_output='word1_output',
                     word_input='word1_input',
                     directive='name')
        word2 = Word(word_output='word2_output',
                     word_input='word2_input',
                     directive=None)

        voc = Vocabulary(word1, [word1, word2], 'fr', 'de')

        words = LearnEngine([], voc, word1)

        self.assertEqual(word1, words.current_word)

        text = 'blabla'
        result = words.guess(text)

        self.assertEqual(text, result.typed_word)
        self.assertEqual(word1, result.word)
        self.assertFalse(result.success)

        self.assertEqual(word2, words.current_word)

        self.assertEqual(0.0, words.accuracy)
        self.assertFalse(words.is_finished)

        words.guess(word2.word_output)
        self.assertEqual(50.0, words.accuracy)
        words.guess(word1.word_output)

        self.assertEqual(50.0, words.accuracy)
        self.assertTrue(words.is_finished)

# -*- coding: utf-8 -*-

import unittest

from learn import Word, Vocabulary, LearnEngine


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

        words = LearnEngine([], self.voc, self.word1)

        self.assertEqual(self.word1, words.current_word)

        text = 'blabla'
        result = words.guess(text)

        self.assertEqual(text, result.typed_word)
        self.assertEqual(self.word1, result.word)
        self.assertFalse(result.success)

        self.assertEqual(self.word2, words.current_word)

        self.assertEqual(0.0, words.accuracy)
        self.assertFalse(words.is_finished)

        words.guess(self.word2.word_output)
        self.assertEqual(50.0, words.accuracy)
        words.guess(self.word1.word_output)

        self.assertEqual(50.0, words.accuracy)
        self.assertTrue(words.is_finished)

    def test_flip_vocabulary(self):
        new_voc = self.voc.flip()

        self.assertEqual(self.word1.flip(), new_voc.name)


if __name__ == '__main__':
    unittest.main(verbosity=3)

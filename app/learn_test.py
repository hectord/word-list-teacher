# -*- coding: utf-8 -*-

from io import StringIO
import unittest

from learn import Word, Vocabulary, Session, normalize


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

    def test_ai_strategy_session_stats(self):
        # the run stats (accuracy, words learned, words left) must work
        # with the ai strategy too, not only the full strategy
        from optimizer import AiStrategy

        session = Session([], self.voc, strategy=AiStrategy())
        first = session.current_word
        other = self.word2 if first is self.word1 else self.word1

        session.guess(first, 'blabla')          # wrong
        self.assertEqual(0.0, session.accuracy)
        # the failed word is recent: the next word must be the other one
        self.assertEqual(other, session.current_word)
        self.assertFalse(session.is_finished)

        session.guess(other, other.word_output)  # right
        self.assertEqual(50.0, session.accuracy)

        session.guess(first, first.word_output)  # right -> last one
        self.assertEqual(50.0, session.accuracy)
        self.assertTrue(session.is_finished)

    def test_summary_statistics(self):
        session = Session([], self.voc, self.word1)

        session.guess(self.word1, 'blabla')              # wrong
        session.guess(self.word2, self.word2.word_output)  # right
        session.guess(self.word1, self.word1.word_output)  # right -> done

        summary = session.summary()
        self.assertEqual({
            'strategy': 'full',
            'words_known': 1,
            'words_total': 2,
            'known_percentage': 50.0,
            'words_to_learn': [{'word': 'word1_output',
                                'input': 'word1_input',
                                'failures': 1}],
        }, summary)

        # the AI strategy adds the counts which changed vs before the run
        summary_ai = session.summary({
            'new_words': 1, 'new_mastered': 1, 'new_hard': 0,
        })
        self.assertEqual(1, summary_ai['new_words'])
        self.assertEqual(1, summary_ai['new_mastered'])
        self.assertEqual(0, summary_ai['new_hard'])

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

    def test_is_other_variant(self):
        word = Word(word_output='die Größe (-n)',
                    word_input='la taille')

        # the expected variant itself (even without the plural note)
        self.assertFalse(word.is_other_variant('die Größe', 'de'))
        # another accepted variant differs from the expected one
        self.assertTrue(word.is_other_variant('die Taille', 'de'))
        # any different text counts too: acceptance is the caller's
        # business (success already proved the answer is correct)
        self.assertTrue(word.is_other_variant('der Tisch', 'de'))

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

    def test_accepts_alternatives(self):
        # the vocabulary data separates alternatives with '/'
        cases = [
            ('das Portemonnaie / Portmonee (-s)',
             ['das Portemonnaie', 'Portmonee', 'das Portmonee']),
            ('er/sie hat ... Augen', ['er hat ... Augen',
                                      'sie hat ... Augen']),
            ('der/die Schneider(in) (Schneider/die Schneiderinnen)',
             ['der Schneider', 'die Schneiderin']),
            ('der Popo/Po', ['der Popo', 'der Po']),
            ('eine Glatze haben/tragen', ['eine Glatze haben', 'tragen']),
            ('sich lehnen gegen/auf', ['sich lehnen gegen',
                                       'sich lehnen auf']),
            ('zu/ins Bett gehen', ['zu Bett gehen', 'ins Bett gehen']),
        ]
        for output, typed in cases:
            word = Word(word_output=output, word_input='x')
            for answer in typed:
                self.assertTrue(word.accepts(answer, 'de'),
                                '%r should accept %r' % (output, answer))

    def test_in_word_parenthesis_is_optional(self):
        word = Word(word_output='der Ell(en)bogen (Ellbogen)',
                    word_input='le coude')
        self.assertTrue(word.accepts('der Ellbogen', 'de'))
        self.assertTrue(word.accepts('der Ellenbogen', 'de'))
        self.assertTrue(word.accepts('der Ell(en)bogen', 'de'))
        self.assertFalse(word.accepts('der Ell bogen', 'de'))

        # a feminine suffix works the same way
        baker = Word(word_output='der/die Bäcker(in) (-)',
                     word_input='le boulanger')
        self.assertTrue(baker.accepts('der Bäcker', 'de'))
        self.assertTrue(baker.accepts('die Bäckerin', 'de'))

        # separable verb marker inside a word
        frozen = Word(word_output='durch(ge)froren', word_input='x')
        self.assertTrue(frozen.accepts('durchgefroren', 'de'))
        self.assertTrue(frozen.accepts('durchfroren', 'de'))

    def test_out_of_word_annotation_is_ignored(self):
        word = Word(word_output='Die Junggeselle (fam)', word_input='x')
        self.assertTrue(word.accepts('Die Junggeselle', 'de'))
        self.assertTrue(word.accepts('Die Junggeselle (fam)', 'de'))
        # the annotation content alone is not part of the word
        self.assertFalse(word.accepts('Die Junggeselle fam', 'de'))

        # plural notes outside a word stay optional too
        plural = Word(word_output='die Beschreibung (-en)', word_input='x')
        self.assertTrue(plural.accepts('die Beschreibung', 'de'))

    def test_nested_parentheses_skip_the_outer_group(self):
        # the female form is an annotation containing a nested group:
        # the whole outer group is skipped, the base form is accepted
        word = Word(word_output='der Schneider (-) (die Schneiderin (-nen))',
                    word_input='le tailleur')
        self.assertTrue(word.accepts('der Schneider', 'de'))
        self.assertTrue(word.accepts(
            'der Schneider (-) (die Schneiderin (-nen))', 'de'))
        self.assertFalse(word.accepts('die Schneiderin', 'de'))
        self.assertNotIn(')', normalize('der Schneider (-) (die Schneiderin (-nen))'))

        # a group attached to the following word stays optional
        web = Word(word_output='das (World-Wide-)Web', word_input='x')
        self.assertTrue(web.accepts('das Web', 'de'))
        self.assertTrue(web.accepts('das World-Wide-Web', 'de'))

    def test_accepts_comma_alternatives(self):
        # a comma separates alternatives just like a slash
        cases = [
            ('der Arzt (-"e), die Ärztin', ['der Arzt', 'die Ärztin']),
            ('mince, maigre', ['mince', 'maigre']),
            ('assez, plutôt', ['assez', 'plutôt']),
        ]
        for output, typed in cases:
            word = Word(word_output=output, word_input='x')
            for answer in typed:
                self.assertTrue(word.accepts(answer, 'de'),
                                '%r should accept %r' % (output, answer))

        # a comma inside an annotation is not a separator
        annotated = Word(word_output='das Wort (fam, dated)',
                         word_input='x')
        self.assertTrue(annotated.accepts('das Wort', 'de'))
        self.assertFalse(annotated.accepts('fam', 'de'))
        self.assertFalse(annotated.accepts('dated', 'de'))

    def test_keys_include_alternatives(self):
        word = Word(word_output='x',
                    word_input='la portefeuille / porte-monnaie')
        self.assertIn('la portefeuille', word.keys)
        self.assertIn('porte-monnaie', word.keys)
        plain = Word(word_output='y', word_input='la portefeuille')
        self.assertTrue(word.keys & plain.keys)

        # commas work the same way on the input side
        comma = Word(word_output='z', word_input='mince, maigre')
        self.assertIn('mince', comma.keys)
        self.assertIn('maigre', comma.keys)

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

    def test_included_levels(self):
        from learn import included_levels

        self.assertEqual(frozenset(['B1']), included_levels('B1'))
        self.assertEqual(frozenset(['B1', 'B2']), included_levels('B2'))
        self.assertEqual(frozenset(['B1', 'B2', 'C1']), included_levels('C1'))
        self.assertIsNone(included_levels(None))
        self.assertIsNone(included_levels('A2'))
        self.assertIsNone(included_levels('X1'))

    def test_flip_keeps_type(self):
        word = Word(word_output='de', word_input='fr', type='noun',
                    level='B1')
        vocabulary = Vocabulary(None, [word], 'fr', 'de')

        flipped = vocabulary.flip()

        self.assertEqual('noun', flipped.words[0].type)
        self.assertEqual('noun', flipped.words[0].flip().type)
        self.assertEqual('B1', flipped.words[0].level)
        self.assertEqual('B1', flipped.words[0].flip().level)

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

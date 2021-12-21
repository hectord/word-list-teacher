# -*- coding: utf-8 -*-

import argparse
from termcolor import colored

from learn import Word, InvalidFileException, Vocabulary, LearnEngine


def say_goodbye():
    print()
    print()
    print('Bye')


def save_words(words: LearnEngine):
    words = words.vocabulary_left

    if not words:
        return

    while True:
        print('Save wrong words?')
        print('filename: ', end='')
        try:
            new_name = input()
            if not new_name:
                break

            with open(new_name, 'a') as f:

                for word in words:
                    f.write(f'{word.line}\n')
                break
        except:
            break


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('filenames', help='words to learn', nargs='+')
    args = parser.parse_args()

    filenames = args.filenames

    all_words = Vocabulary()

    for filename in filenames:
        vocabulary = Vocabulary.load(filename)
        all_words.add(vocabulary)

    learn = LearnEngine(all_words)

    try:

        while not learn.is_finished:
            current_word = learn.current_word

            german, french = current_word.word_output, current_word.word_input

            print(f'> {french}')
            print(f'? ', end='')
            word_given = input()

            if learn.guess(word_given):

                if current_word.is_complex:
                    print(colored('Great :)', 'green'), ' ',
                          colored(german, 'green', attrs=['bold']))
                else:
                    print(colored('Great :)', 'green'))
            else:
                print(colored(f'! {german}', 'red', attrs=['bold']))

            print()

        print()
        print("new words learned =", learn.new_words_learned)
        print("accuracy =", learn.accuracy)
        print("filename =", ' '.join(filenames))
        print()

        save_words(learn)
    except KeyboardInterrupt:
        print()
        print()
        save_words(learn)
        say_goodbye()
    except EOFError:
        say_goodbye()
    except InvalidFileException as e:
        print(e)

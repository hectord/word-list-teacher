# -*- coding: utf-8 -*-

import os.path
from typing import Set
import getpass

import argparse
from termcolor import colored

from learn import Word, InvalidFileException, Vocabulary, LearnEngine
from store import load_database


def say_goodbye():
    print()
    print()
    print('Bye')


def save_words(words: LearnEngine):
    words = words.vocabulary_left

    if not words:
        return

    for word in words:
        print(f'{word.word_input:20} {word.word_output:20}')

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


def learn(files: Set[str], vocabulary: Vocabulary):
    engine = LearnEngine(all_words)

    try:

        while not engine.is_finished:
            current_word = engine.current_word

            german, french = current_word.word_output, current_word.word_input

            print(f'> {french}')
            print(f'? ', end='')
            word_given = input()

            if engine.guess(word_given):

                if current_word.is_complex:
                    print(colored('Great :)', 'green'), ' ',
                          colored(german, 'green', attrs=['bold']))
                else:
                    print(colored('Great :)', 'green'))
            else:
                print(colored(f'! {german}', 'red', attrs=['bold']))

            print()

        print()
        print("new words learned =", engine.new_words_learned)
        print("accuracy =", engine.accuracy)
        print("filename =", ' '.join(sorted(files)))
        print()

        save_words(engine)
    except KeyboardInterrupt:
        print()
        print()
        save_words(engine)
        say_goodbye()
    except EOFError:
        say_goodbye()
    except InvalidFileException as e:
        print(e)


def vocabulary_name(path: str):
    try:
        vocabulary = Vocabulary.load(path)

        return f'{vocabulary.name.word_input} ({len(vocabulary)} words)'
    except IsADirectoryError:
        return colored('is a directory', 'red')
    except InvalidFileException as e:
        return colored(f'invalid file ({e})', 'red')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    subparser = parser.add_subparsers(dest='cmd', required=True)

    list_subparser = subparser.add_parser('list')
    list_subparser.add_argument('files', help='vocs to list', nargs='+')

    learn_subparser = subparser.add_parser('learn')
    learn_subparser.add_argument('files', help='words to learn', nargs='+')

    learn_subparser = subparser.add_parser('load')
    learn_subparser.add_argument('database', help='database path', nargs=1)
    learn_subparser.add_argument('files', help='words to load', nargs='+')

    learn_subparser = subparser.add_parser('create-user')
    learn_subparser.add_argument('database', help='database path', nargs=1)
    learn_subparser.add_argument('username', help='new username', nargs=1)

    args = parser.parse_args()

    if args.cmd == 'list':
        files = args.files

        for path in sorted(files):
            filename = os.path.basename(path)
            print(f' - {filename}: {vocabulary_name(path)}')

    elif args.cmd == 'learn':
        files = args.files
        all_words = Vocabulary()

        for filename in files:
            vocabulary = Vocabulary.load(filename)
            all_words.add(vocabulary)

        learn(set(files), all_words)
    elif args.cmd == 'load':
        files = args.files
        database = args.database[0]
        database = load_database(database)

        for filename in files:
            vocabulary = Vocabulary.load(filename)
            database.create_vocabulary(vocabulary)
    elif args.cmd == 'create-user':
        username = args.username[0]

        database = args.database[0]
        database = load_database(database)

        password = getpass.getpass()

        database.create_user(username, password)
    else:
        assert False

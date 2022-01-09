# -*- coding: utf-8 -*-

import os.path
from typing import Set
import getpass
import sys

import argparse
from termcolor import colored

from learn import Word, InvalidFileException, Vocabulary, Session
from learn import Language
from store import load_database


def say_goodbye():
    print()
    print()
    print('Bye')


def save_words(words: Session):
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
    session = Session([], all_words)

    try:

        while not session.is_finished:
            current_word = session.current_word

            german, french = current_word.word_output, current_word.word_input

            print(f'> {french}')
            print(f'? ', end='')
            word_given = input()

            attempts = session.guess(current_word, word_given)

            if attempts.success:
                current_word = attempts.word

                if current_word.is_complex:
                    print(colored('Great :)', 'green'), ' ',
                          colored(german, 'green', attrs=['bold']))
                else:
                    print(colored('Great :)', 'green'))
            else:
                print(colored(f'! {german}', 'red', attrs=['bold']))

            print()

        print()
        print("new words learned =", session.new_words_learned)
        print("accuracy =", session.accuracy)
        print("filename =", ' '.join(sorted(files)))
        print()

        save_words(session)
    except KeyboardInterrupt:
        print()
        print()
        save_words(session)
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
    cmdparser = parser.add_subparsers(dest='cmd', required=True)

    list_subparser = cmdparser.add_parser('list')
    list_subparser.add_argument('files', help='vocs to list', nargs='+')

    learn_subparser = cmdparser.add_parser('learn')
    learn_subparser.add_argument('files', help='words to learn', nargs='+')

    dbparser = cmdparser.add_parser('database')
    dbparser.add_argument('database', help='database path', nargs=1)
    db_subparser = dbparser.add_subparsers(dest='db_cmd', required=True)

    add_vocabulary_subparser = db_subparser.add_parser('add-vocabulary')
    add_vocabulary_subparser.add_argument('files', help='words to load', nargs='+')

    create_user_subparser = db_subparser.add_parser('create-user')
    create_user_subparser.add_argument('username', help='new username', nargs=1)
    create_user_subparser.add_argument('--speaks', help='language spoken', nargs='+')

    db_subparser.add_parser('list-vocabularies')
    list_words_subparser = db_subparser.add_parser('list-words')
    list_words_subparser.add_argument('voc-id', help='vocabulary ID', nargs=1, type=int)

    remove_vocabulary_subparser = db_subparser.add_parser('remove-vocabulary')
    remove_vocabulary_subparser.add_argument('voc-id', help='vocabulary ID', nargs=1, type=int)

    add_word_subparser = db_subparser.add_parser('add-word')
    add_word_subparser.add_argument('voc-id', nargs=1, type=int)
    add_word_subparser.add_argument('word-input', nargs=1)
    add_word_subparser.add_argument('word-output', nargs=1)

    db_subparser.add_parser('init')

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
    elif args.db_cmd == 'add-vocabulary':
        files = args.files
        database = args.database[0]
        database = load_database(database)

        for filename in files:
            vocabulary = Vocabulary.load(filename)
            database.create_vocabulary(vocabulary)

    elif args.db_cmd == 'create-user':
        username = args.username[0]

        database = args.database[0]
        database = load_database(database)

        password = getpass.getpass()

        languages = set()
        for language_code in args.speaks:
            language = Language.from_code(language_code)

            if language is None:
                print("invalid code", file=sys.stdout)
                sys.exit(-1)
            languages.add(language)

        database.create_user(username, password, languages)

    elif args.db_cmd == 'init':
        database = args.database[0]
        database = load_database(database)

        for language in Language:
            database.create_language(language)
    elif args.db_cmd == 'list-vocabularies':
        database = args.database[0]
        database = load_database(database)

        for voc_id, voc in database.list_vocabularies_for(None).items():
            print(voc_id, voc)
    elif args.db_cmd == 'list-words':
        database = args.database[0]
        database = load_database(database)

        voc_id = vars(args)['voc-id'][0]

        voc = database.get_vocabulary(None, voc_id)

        if voc is None:
            print("no vocabulary found", file=sys.stderr)
            sys.exit(1)

        for word in voc.words:
            word_id = voc.word_id(word)
            print('%4d %30s %30s' % (word_id, word.word_output, word.word_input))

    elif args.db_cmd == 'remove-vocabulary':
        database = args.database[0]
        database = load_database(database)

        args = vars(args)
        voc_id = args['voc-id'][0]

        voc = database.get_vocabulary(None, voc_id)

        if voc is None:
            print("no vocabulary found", file=sys.stderr)
            sys.exit(1)

        database.remove_vocabulary(voc)

    elif args.db_cmd == 'add-word':
        database = args.database[0]
        database = load_database(database)

        args = vars(args)
        voc_id = args['voc-id'][0]
        word_input = args['word-input'][0]
        word_output = args['word-output'][0]

        voc = database.get_vocabulary(None, voc_id)

        if voc is None:
            print("no vocabulary found", file=sys.stderr)
            sys.exit(1)

        word = Word(word_input=word_input,
                    word_output=word_output,
                    directive=None)
        database.add_word(voc, word)

    else:
        assert False

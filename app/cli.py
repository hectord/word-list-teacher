# -*- coding: utf-8 -*-

import os.path
from typing import List, Set
import getpass
import sys
import csv
import re

import argparse
from termcolor import colored

from learn import Word, InvalidFileException, Vocabulary, Session
from learn import Language
from store import load_database, DbException


def load_dictionary(filename: str,
                    input_language: str = 'fr',
                    output_language: str = 'de') -> List[Vocabulary]:
    """
    Load a cleaned dictionary file like data/merged.cleaned:

        vocabulary;section;german;translation
        1 Beschreibung von Menschen;;sein*;être
        2 Kleidung und Mode;Verbs;tragen;porter

    The dictionary is assumed to be German -> French. Each distinct
    vocabulary name becomes a separate Vocabulary (named after it);
    non-empty section names become sections inside it.
    """
    by_vocabulary = {}

    with open(filename, encoding='utf-8') as f:
        for row in csv.reader(f, delimiter=';'):
            if len(row) != 4:
                continue

            vocabulary, section, word, translation = \
                (field.strip() for field in row)

            if vocabulary == 'vocabulary':
                continue
            if not word or not translation:
                continue

            by_vocabulary.setdefault(vocabulary, []).append(
                (section, word, translation))

    if not by_vocabulary:
        raise InvalidFileException(f'no words found in {filename}')

    vocabularies = []
    for vocabulary, entries in by_vocabulary.items():
        words = []
        word_sections = []
        current_section = None

        for section, word, translation in entries:
            if section != current_section:
                current_section = section

            words.append(Word(word_output=word,
                              word_input=translation))
            word_sections.append(current_section or None)

        name = Word(word_output=vocabulary,
                    word_input=vocabulary)
        vocabularies.append(Vocabulary(name, words,
                                       input_language=input_language,
                                       output_language=output_language,
                                       sections=word_sections))

    return vocabularies


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

    add_dictionary_subparser = db_subparser.add_parser('add-dictionary')
    add_dictionary_subparser.add_argument('files', help='cleaned dictionary CSV files (vocabulary;section;word;translation)', nargs='+')

    create_user_subparser = db_subparser.add_parser('create-user')
    create_user_subparser.add_argument('username', help='new username', nargs=1)
    create_user_subparser.add_argument('--main-language', required=True,
                                       help='language the user knows',
                                       nargs=1)
    create_user_subparser.add_argument('--level', nargs=1,
                                       help='level: A2, B1, B2 or C1')

    set_level_subparser = db_subparser.add_parser('set-user-level')
    set_level_subparser.add_argument('email', help='user email', nargs=1)
    set_level_subparser.add_argument('level', help='A2, B1, B2 or C1', nargs=1)

    db_subparser.add_parser('list-users')

    update_user_subparser = db_subparser.add_parser('update-user')
    update_user_subparser.add_argument('email', help='user email', nargs=1)
    update_user_subparser.add_argument('--main-language', nargs='?',
                                       help='language the user knows')
    update_user_subparser.add_argument('--level', nargs='?',
                                       help='A2, B1, B2 or C1')
    update_user_subparser.add_argument('--password', action='store_true',
                                       help='prompt for a new password')

    db_subparser.add_parser('list-vocabularies')
    list_words_subparser = db_subparser.add_parser('list-words')
    list_words_subparser.add_argument('voc-id', help='vocabulary ID', nargs=1, type=int)

    list_sections_subparser = db_subparser.add_parser('list-sections')
    list_sections_subparser.add_argument('voc-id', help='vocabulary ID', nargs=1, type=int)

    remove_vocabulary_subparser = db_subparser.add_parser('remove-vocabulary')
    remove_vocabulary_subparser.add_argument('voc-id', help='vocabulary ID', nargs=1, type=int)

    update_word_subparser = db_subparser.add_parser('update-word')
    update_word_subparser.add_argument('word-id', nargs=1, type=int)
    update_word_subparser.add_argument('--language',
                                       help='language of the text')
    update_word_subparser.add_argument('--text', nargs='?')
    update_word_subparser.add_argument('--example', nargs='?')
    update_word_subparser.add_argument('--type', dest='word_type', nargs='?',
                                       help='noun, verb, adjective, ...')
    update_word_subparser.add_argument('--level', dest='word_level', nargs='?',
                                       help='A2, B1, B2 or C1')

    add_word_subparser = db_subparser.add_parser('add-word')
    add_word_subparser.add_argument('voc-id', nargs=1, type=int)
    add_word_subparser.add_argument('--input-language', required=True)
    add_word_subparser.add_argument('--output-language', required=True)
    add_word_subparser.add_argument('--type', dest='word_type', nargs='?')
    add_word_subparser.add_argument('--level', dest='word_level', nargs='?')
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
            with open(filename) as f:
                vocabulary = Vocabulary.load(f)
            all_words.add(vocabulary)

        learn(set(files), all_words)
    elif args.db_cmd == 'add-vocabulary':
        files = args.files
        database = args.database[0]
        database = load_database(database)

        for filename in files:
            with open(filename) as f:
                vocabulary = Vocabulary.load(f)
            database.create_vocabulary(vocabulary)

    elif args.db_cmd == 'add-dictionary':
        database = args.database[0]
        database = load_database(database)

        for filename in args.files:
            for vocabulary in load_dictionary(filename):
                voc_id = database.create_vocabulary(vocabulary)
                print('%s: %d words, %d sections -> vocabulary %d %r'
                      % (filename, len(vocabulary),
                         len(vocabulary.sections), voc_id,
                         vocabulary.name.word_input))

    elif args.db_cmd == 'create-user':
        username = args.username[0]

        database = args.database[0]
        database = load_database(database)

        password = getpass.getpass()

        language = Language.from_code(args.main_language[0])
        if language is None:
            print("invalid language code", file=sys.stderr)
            sys.exit(-1)

        level = args.level[0] if args.level else None
        database.create_user(username, password, language, level=level)

    elif args.db_cmd == 'set-user-level':
        database = args.database[0]
        database = load_database(database)

        try:
            database.set_user_level(args.email[0], args.level[0])
        except DbException as e:
            print(e, file=sys.stderr)
            sys.exit(1)

        print('updated level of', args.email[0])

    elif args.db_cmd == 'list-users':
        database = args.database[0]
        database = load_database(database)

        for user in database.list_user_details():
            print('%4d  %-32s %-5s %-4s'
                  % (user['id'], user['email'],
                     user['main_language'] or '-',
                     user['level'] or '-'))

    elif args.db_cmd == 'update-user':
        database = args.database[0]
        database = load_database(database)

        email = args.email[0]

        main_language = None
        if args.main_language:
            main_language = Language.from_code(args.main_language)
            if main_language is None:
                print("invalid language code", file=sys.stderr)
                sys.exit(-1)

        level = args.level if args.level else None
        password = getpass.getpass() if args.password else None

        try:
            database.update_user(email, main_language=main_language,
                                 level=level, password=password)
        except DbException as e:
            print(e, file=sys.stderr)
            sys.exit(1)

        print('updated', email)

    elif args.db_cmd == 'init':
        database = args.database[0]
        database = load_database(database)

        for language in Language:
            database.create_language(language)
    elif args.db_cmd == 'list-vocabularies':
        database = args.database[0]
        database = load_database(database)

        for summary in database.vocabulary_summaries():
            title = next(iter(summary['titles'].values()), '-')
            print('%4d %5d words  %s'
                  % (summary['id'], summary['size'], title))

    elif args.db_cmd == 'list-sections':
        database = args.database[0]
        database = load_database(database)

        voc_id = vars(args)['voc-id'][0]

        for section_id, texts in \
                database.list_section_texts(voc_id).items():
            print('%4d %s'
                  % (section_id,
                     ' | '.join('%s: %s' % (code, text)
                                for code, text in texts.items())))

    elif args.db_cmd == 'list-words':
        database = args.database[0]
        database = load_database(database)

        voc_id = vars(args)['voc-id'][0]

        for word_id, texts in database.list_word_texts(voc_id).items():
            print('%4d %s'
                  % (word_id,
                     ' | '.join('%s: %s' % (code, data['text'])
                                for code, data in texts.items())))

    elif args.db_cmd == 'remove-vocabulary':
        database = args.database[0]
        database = load_database(database)

        args = vars(args)
        voc_id = args['voc-id'][0]

        database.remove_vocabulary(voc_id)

    elif args.db_cmd == 'add-word':
        database = args.database[0]
        database = load_database(database)

        args = vars(args)
        voc_id = args['voc-id'][0]
        input_code = args['input_language']
        output_code = args['output_language']
        word_input = args['word-input'][0]
        word_output = args['word-output'][0]

        word = Word(word_input=word_input,
                    word_output=word_output,
                    type=args['word_type'],
                    level=args['word_level'])
        database.add_word(voc_id, input_code, output_code, word)

    elif args.db_cmd == 'update-word':
        database = args.database[0]
        database = load_database(database)

        args = vars(args)
        word_id = args['word-id'][0]
        language = args['language']
        word_type = args['word_type']
        word_level = args['word_level']
        text = args['text'] if args['text'] else None
        example = args['example'] if args['example'] else None

        if word_type is not None:
            database.update_word_type(word_id, word_type)
        if word_level is not None:
            database.update_word_level(word_id, word_level)
        if language is not None:
            database.update_word_text(word_id, language,
                                      text=text, example=example)

    else:
        assert False

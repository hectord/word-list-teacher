# -*- coding: utf-8 -*-

from typing import Set
from datetime import date
from peewee import *

from learn import Vocabulary, Word

db = SqliteDatabase(None)


class DbVocabulary(Model):

    class Meta:
        database = db


class DbWord(Model):
    vocabulary = ForeignKeyField(DbVocabulary, backref='words')
    word_input = CharField()
    word_output = CharField()
    directive = CharField(null=True)

    class Meta:
        database = db


class Database:

    def create_vocabulary(self, voc: Vocabulary):
        new_voc = DbVocabulary.create()

        for word in voc.words:
            DbWord.create(vocabulary=new_voc,
                          word_input=word.word_input,
                          word_output=word.word_output,
                          directive=word.directive)

    def list_vocabularies(self) -> Set[Vocabulary]:
        vocs = set()

        for voc in DbVocabulary.select():
            name = None
            words = set()

            for word in voc.words:
                new_word = Word(word_input=word.word_input,
                                word_output=word.word_output,
                                directive=word.directive)

                if new_word.is_name:
                    name = new_word
                words.add(new_word)

            vocs.add(Vocabulary(name, words))

        return vocs


def load_database(name: str) -> Database:
    db.init(name)
    db.connect()
    db.create_tables([DbVocabulary, DbWord])

    return Database()

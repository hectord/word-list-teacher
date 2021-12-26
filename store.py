# -*- coding: utf-8 -*-

from security import check_password, get_hashed_password
from typing import Dict
from datetime import date
from peewee import *

from learn import Vocabulary, Word

db = SqliteDatabase(None)


class DbException(Exception):
    pass


class DbUser(Model):
    email = CharField()
    password = CharField()

    class Meta:
        database = db


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

    def get_user(self, email: str, password: str) -> DbUser:
        users = list(DbUser.select().where(DbUser.email == email))

        if not users or not check_password(password, users[0].password):
            raise DbException('user not found')

        return users[0]

    def create_user(self, email: str, password: str) -> DbUser:
        users = list(DbUser.select().where(DbUser.email == email))

        if users:
            raise DbException('user already exists')

        hash_password = get_hashed_password(password)

        new_user = DbUser.create(email=email,
                                 password=hash_password)
        return new_user

    def create_vocabulary(self, voc: Vocabulary):
        new_voc = DbVocabulary.create()

        for word in voc.words:
            DbWord.create(vocabulary=new_voc,
                          word_input=word.word_input,
                          word_output=word.word_output,
                          directive=word.directive)

    def list_vocabularies(self) -> Dict[int, Vocabulary]:
        vocs = {}

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

            vocs[voc.id] = Vocabulary(name, words)

        return vocs


def load_database(name: str) -> Database:
    db.init(name)
    db.connect()
    db.create_tables([DbVocabulary, DbWord, DbUser])

    return Database()

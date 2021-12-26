# -*- coding: utf-8 -*-

from security import check_password, get_hashed_password
from typing import Dict, Optional
from datetime import date, datetime
from peewee import *

from learn import Vocabulary, Word, LearnEngine

db = SqliteDatabase(None)


class DbException(Exception):
    pass


class DbUser(Model):
    email = CharField()
    password = CharField()

    class Meta:
        database = db


class DbSession(Model):
    user = ForeignKeyField(DbUser, backref='sessions')
    creation = DateTimeField()

    class Meta:
        database = db


class DbVocabulary(Model):

    class Meta:
        database = db


class DbVocabularySession(Model):
    session = ForeignKeyField(DbSession, backref='vocabularies')
    vocabulary = ForeignKeyField(DbVocabulary, backref='sessions')

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

    def create_new_session(self,
                           user: DbUser,
                           voc: Vocabulary) -> int:

        new_session = DbSession.create(user=user.id,
                                       creation=datetime.now())

        DbVocabularySession.create(session=new_session,
                                   vocabulary=voc.id)
        return new_session.id

    def last_session(self, voc: Vocabulary) -> Optional[LearnEngine]:

        if voc.id is None:
            return None

        sessions = (DbVocabularySession
                    .select()
                    .join(DbSession)
                    .where(DbVocabularySession.vocabulary == voc.id)
                    .order_by(DbSession.id)
                    .limit(1))
        sessions = list(sessions)

        if not sessions:
            return None
        session_to_load = sessions[0]

        return self.load_session(session_to_load.id)

    def load_session(self, session_id: int) -> LearnEngine:
        v = Vocabulary(None, set())

        for vocabulary in (DbVocabulary
                           .select()
                           .join(DbVocabularySession)
                           .join(DbSession)
                           .where(DbSession.id == session_id)):
            v.add(self._load_vocabulary(vocabulary))

        ret = LearnEngine([], v)
        ret.set_id(session_id)
        return ret

    def create_vocabulary(self, voc: Vocabulary) -> int:
        new_voc = DbVocabulary.create()

        for word in voc.words:
            DbWord.create(vocabulary=new_voc,
                          word_input=word.word_input,
                          word_output=word.word_output,
                          directive=word.directive)

        voc.set_id(new_voc.id)
        return new_voc.id

    def _load_vocabulary(self, voc: DbVocabulary) -> Vocabulary:
        name = None
        words = set()

        for word in voc.words:
            new_word = Word(word_input=word.word_input,
                            word_output=word.word_output,
                            directive=word.directive)

            if new_word.is_name:
                name = new_word
            words.add(new_word)

        ret = Vocabulary(name, words)
        ret.set_id(voc)
        return ret

    def get_vocabulary(self, id: int) -> Vocabulary:
        voc = DbVocabulary.get(id)

        return self._load_vocabulary(voc)

    def list_vocabularies(self) -> Dict[int, Vocabulary]:
        vocs = {}

        for voc in DbVocabulary.select():
            vocs[voc.id] = self._load_vocabulary(voc)

        return vocs


def load_database(name: str) -> Database:
    db.init(name)
    db.connect()
    db.create_tables([DbVocabulary, DbWord, DbUser,
                      DbVocabularySession, DbSession])

    return Database()

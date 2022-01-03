# -*- coding: utf-8 -*-

from security import check_password, get_hashed_password
from typing import Dict, Optional, Set
from datetime import date, datetime
from peewee import *

from learn import Vocabulary, Word, LearnEngine, WordAttempt
from learn import Language, User

db = SqliteDatabase(None)


class DbException(Exception):
    pass


class DbLanguage(Model):
    code = CharField(primary_key=True)
    name = CharField()

    class Meta:
        database = db


class DbUser(Model):
    email = CharField()
    password = CharField()

    class Meta:
        database = db


class DbSpeak(Model):
    language = ForeignKeyField(DbLanguage, backref='spoken_by')
    user = ForeignKeyField(DbUser, backref='speaks')

    class Meta:
        database = db


class DbVocabulary(Model):
    input_language = ForeignKeyField(DbLanguage)
    output_language = ForeignKeyField(DbLanguage)

    class Meta:
        database = db


class DbWord(Model):
    vocabulary = ForeignKeyField(DbVocabulary, backref='words')
    word_input = CharField()
    word_output = CharField()
    directive = CharField(null=True)

    class Meta:
        database = db


class DbSession(Model):
    user = ForeignKeyField(DbUser, backref='sessions')
    current_word = ForeignKeyField(DbWord, null=True)
    creation = DateTimeField()
    finished = BooleanField()

    class Meta:
        database = db


class DbVocabularySession(Model):
    session = ForeignKeyField(DbSession, backref='vocabularies')
    vocabulary = ForeignKeyField(DbVocabulary, backref='sessions')
    flipped = BooleanField()

    class Meta:
        database = db


class DbWordAttempt(Model):
    word = ForeignKeyField(DbWord, backref='attempts')
    session = ForeignKeyField(DbSession, backref='attempts')
    typed_word = CharField()
    success = BooleanField()
    time = DateTimeField()

    class Meta:
        database = db


class Database:

    def create_language(self, language: Language):
        code = language.code
        name = language.name

        DbLanguage.create(code=code, name=name)

    def get_user(self, email: str, password: str) -> DbUser:
        users = list(DbUser.select().where(DbUser.email == email))

        if not users or not check_password(password, users[0].password):
            raise DbException('user not found')

        db_user = users[0]
        languages = set()

        for speak in DbSpeak.select().where(DbSpeak.user == db_user):
            languages.add(Language.from_code(speak.language.code))

        return User(email=email, password=password, languages_spoken=languages)

    def create_user(self,
                    email: str,
                    password: str,
                    languages: Set[Language]) -> User:
        users = list(DbUser.select().where(DbUser.email == email))

        if users:
            raise DbException('user already exists')

        hash_password = get_hashed_password(password)

        new_user = DbUser.create(email=email,
                                 password=hash_password)

        for language in languages:
            language = DbLanguage.get(code=language.code)
            DbSpeak.create(language=language, user=new_user)

        return self.get_user(email, password)

    def _get_db_user(self, user: User) -> DbUser:
        return DbUser.get(email=user.email)

    def create_new_session(self,
                           user: User,
                           voc: Vocabulary) -> LearnEngine:
        db_user = self._get_db_user(user)
        new_session = LearnEngine([], voc)

        new_db_session = DbSession.create(user=db_user.id,
                                          creation=datetime.now(),
                                          finished=len(voc) == 0)
        new_session.set_id(new_db_session.id)
        DbVocabularySession.create(session=new_db_session,
                                   vocabulary=voc.id,
                                   flipped=voc.is_flipped)
        current_db_word = self._get_db_word(new_session,
                                            new_session.current_word)
        db_session = DbSession.get(new_db_session.id)
        db_session.current_word = current_db_word
        db_session.save()

        return new_session

    def _get_db_word(self,
                     session: LearnEngine,
                     word: Word) -> Optional[DbWord]:

        word_input, word_output = word.word_input, word.word_output

        if session.is_flipped:
            word_input, word_output = word_output, word_input

        for row in (DbWord.select()
                    .join(DbVocabulary)
                    .join(DbVocabularySession)
                    .join(DbSession)
                    .where(DbSession.id == session.id)
                    .where(DbWord.word_input == word_input)
                    .where(DbWord.word_output == word_output)):
            return row

        assert False
        return None

    def add_word(self,
                 session: LearnEngine,
                 word_attempt: WordAttempt):
        session_id = session.id
        word = word_attempt.word

        db_session = DbSession.get(session_id)

        if session.current_word is None:
            db_session.current_word = None
        else:
            current_word = session.current_word
            db_session.current_word = self._get_db_word(session, current_word)

        db_session.finished = session.is_finished
        db_session.save()

        db_word = self._get_db_word(session, word)

        DbWordAttempt.create(word=db_word.id,
                             typed_word=word_attempt.typed_word,
                             session=session_id,
                             time=datetime.now(),
                             success=word_attempt.success)

    def last_session(self,
                     user: User,
                     voc: Vocabulary,
                     finished: bool = None) -> Optional[LearnEngine]:
        db_user = self._get_db_user(user)

        if voc.id is None:
            return None

        sessions = (DbSession
                    .select()
                    .join(DbVocabularySession)
                    .where(DbSession.user == db_user)
                    .where(DbVocabularySession.vocabulary == voc.id))

        if finished is not None:
            sessions = sessions.where(DbSession.finished == finished)

        sessions = sessions.order_by(DbSession.id.desc())
        sessions = list(sessions)

        if not sessions:
            return None
        session_to_load = sessions[0]

        return self.load_session(session_to_load.id)

    def load_session(self, session_id: int) -> LearnEngine:
        v = Vocabulary(None, set())

        db_session = DbSession.get(session_id)
        flipped = False

        for db_voc_session in (DbVocabularySession
                               .select()
                               .where(DbVocabularySession.session == session_id)):
            voc = self._load_vocabulary(db_voc_session.vocabulary)

            if db_voc_session.flipped:
                flipped = True
            v.add(voc)

        if flipped:
            v = v.flip()

        attempts = []

        for attempt in (DbWordAttempt
                        .select()
                        .where(DbWordAttempt.session == session_id)
                        .order_by(DbWordAttempt.id.asc())):

            word = self._create_word_from(attempt.word)

            if flipped:
                word = word.flip()

            attempt = WordAttempt(word=word,
                                  typed_word=attempt.typed_word,
                                  success=attempt.success,
                                  time=attempt.time)

            attempts.append(attempt)

        current_word = None
        if db_session.current_word is not None:
            current_word = self._create_word_from(db_session.current_word)
            if flipped:
                current_word = current_word.flip()

        ret = LearnEngine(attempts, v, current_word=current_word)
        ret.set_id(session_id)
        return ret

    def create_vocabulary(self, voc: Vocabulary) -> int:
        input_language = DbLanguage.get(code=voc.input_language)
        output_language = DbLanguage.get(code=voc.output_language)

        new_voc = DbVocabulary.create(input_language=input_language,
                                      output_language=output_language)

        for word in voc.words:
            DbWord.create(vocabulary=new_voc,
                          word_input=word.word_input,
                          word_output=word.word_output,
                          directive=word.directive)

        voc.set_id(new_voc.id)
        return new_voc.id

    def _create_word_from(self, word: DbWord) -> Word:
        return Word(word_input=word.word_input,
                    word_output=word.word_output,
                    directive=word.directive)

    def _load_vocabulary(self, voc: DbVocabulary) -> Vocabulary:
        name = None
        words = []

        for word in voc.words:
            new_word = self._create_word_from(word)

            if new_word.is_name:
                name = new_word

            words.append(new_word)

        input_language = voc.input_language.code
        output_language = voc.output_language.code

        ret = Vocabulary(name, words, input_language, output_language)
        ret.set_id(voc.id)
        return ret

    def get_vocabulary(self, user: User, voc_id: int) -> Vocabulary:
        vocs = self.list_vocabularies(user)

        return vocs[voc_id]

    def list_vocabularies(self, user: User) -> Dict[int, Vocabulary]:
        vocs = {}

        for voc in DbVocabulary.select():
            input_language = Language.from_code(voc.input_language.code)
            output_language = Language.from_code(voc.output_language.code)

            know_input = input_language in user.languages_spoken
            know_output = output_language in user.languages_spoken

            if know_input == know_output:
                continue

            voc = self._load_vocabulary(voc)

            if know_output:
                voc = voc.flip()

            vocs[voc.id] = voc

        return vocs


def load_database(name: str) -> Database:
    db.init(name)
    db.connect()
    db.create_tables([DbVocabulary, DbWord, DbUser,
                      DbVocabularySession, DbSession,
                      DbWordAttempt, DbLanguage, DbSpeak])

    return Database()

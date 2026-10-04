# -*- coding: utf-8 -*-

from collections import defaultdict
import hashlib
import time

from security import check_password, get_hashed_password
from datetime import datetime

from peewee import *

# note: import typing after peewee (peewee shadows its own ``Tuple`` helper)
from typing import Dict, List, Optional, Tuple

from learn import Vocabulary, Word, Session, WordAttempt
from learn import Language, User, VocabularyStats, included_levels
from learn import make_strategy

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
    main_language = ForeignKeyField(DbLanguage, null=True)
    level = CharField(null=True)
    target_language = ForeignKeyField(DbLanguage, null=True, backref='+')
    strategy = CharField(null=True)

    class Meta:
        database = db


class DbVocabulary(Model):
    """A vocabulary is language agnostic; its texts live in the
    title/section/word-text entities below."""

    class Meta:
        database = db


class DbVocabularyTitle(Model):
    vocabulary = ForeignKeyField(DbVocabulary, backref='titles')
    language = ForeignKeyField(DbLanguage)
    title = CharField()

    class Meta:
        database = db


class DbSection(Model):
    vocabulary = ForeignKeyField(DbVocabulary, backref='sections')

    class Meta:
        database = db


class DbSectionText(Model):
    section = ForeignKeyField(DbSection, backref='texts')
    language = ForeignKeyField(DbLanguage)
    text = CharField()

    class Meta:
        database = db


class DbWord(Model):
    vocabulary = ForeignKeyField(DbVocabulary, backref='words')
    section = ForeignKeyField(DbSection, null=True, backref='words')
    type = CharField(null=True)
    # level of the word (B1, B2, C1); same for every language
    level = CharField(null=True)

    class Meta:
        database = db


class DbWordText(Model):
    word = ForeignKeyField(DbWord, backref='texts')
    language = ForeignKeyField(DbLanguage)
    text = CharField()
    example = CharField(null=True, max_length=1024)

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
    input_language = ForeignKeyField(DbLanguage)
    output_language = ForeignKeyField(DbLanguage)
    section = ForeignKeyField(DbSection, null=True)
    level = CharField(null=True)

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


def _code(language) -> Optional[str]:
    if language is None:
        return None
    return language.code if isinstance(language, Language) else language


# Successful HTTP Basic auth is cached: bcrypt is intentionally slow
# (~0.4s) and the browser re-sends the credentials on every request.
# Entries are keyed by email and hold a hash of the credentials so the
# password itself is not kept around.
_AUTH_CACHE = {}
_AUTH_CACHE_TTL = 300.0


def _credentials_hash(email: str, password: str) -> str:
    return hashlib.sha256(('%s\0%s' % (email, password))
                          .encode('utf-8')).hexdigest()


class Database:

    # ------------------------------------------------------------- languages
    def create_language(self, language: Language):
        DbLanguage.create(code=language.code, name=language.name)

    def languages(self) -> List[Language]:
        return [Language.from_code(row.code)
                for row in DbLanguage.select().order_by(DbLanguage.code)]

    def target_languages(self, language_code: str) -> List[Language]:
        """Languages a word can be translated to, starting from
        ``language_code`` (i.e. languages sharing at least one word)."""
        rows = db.execute_sql(
            'SELECT DISTINCT t2.language_id FROM dbwordtext t1 '
            'JOIN dbwordtext t2 ON t1.word_id = t2.word_id '
            'WHERE t1.language_id = ? AND t2.language_id != ?',
            (language_code, language_code)).fetchall()

        languages = [Language.from_code(row[0]) for row in rows]
        languages = [l for l in languages if l is not None]
        languages.sort(key=lambda l: l.name)
        return languages

    # ----------------------------------------------------------------- users
    def get_user(self, email: str, password: str) -> User:
        credentials = _credentials_hash(email, password)
        now = time.monotonic()

        cached = _AUTH_CACHE.get(email)
        if cached is not None and cached[0] == credentials \
                and cached[1] > now:
            return cached[2]

        users = list(DbUser.select().where(DbUser.email == email))

        if not users or not check_password(password, users[0].password):
            raise DbException('user not found')

        db_user = users[0]
        main_language = None
        if db_user.main_language is not None:
            main_language = Language.from_code(db_user.main_language.code)

        target_language = None
        if db_user.target_language is not None:
            target_language = Language.from_code(db_user.target_language.code)

        user = User(email=email, password=password,
                    main_language=main_language,
                    level=db_user.level,
                    target_language=target_language,
                    strategy=db_user.strategy or 'full')

        _AUTH_CACHE[email] = (credentials, now + _AUTH_CACHE_TTL, user)
        return user

    def create_user(self,
                    email: str,
                    password: str,
                    main_language: Optional[Language] = None,
                    level: Optional[str] = None,
                    target_language: Optional[Language] = None) -> User:
        if DbUser.select().where(DbUser.email == email).count():
            raise DbException('user already exists')

        hash_password = get_hashed_password(password)

        language = None
        if main_language is not None:
            language = DbLanguage.get(code=main_language.code)

        target = None
        if target_language is not None:
            target = DbLanguage.get(code=target_language.code)

        DbUser.create(email=email,
                      password=hash_password,
                      main_language=language,
                      level=level,
                      target_language=target)

        return self.get_user(email, password)

    def set_user_strategy(self, user, strategy: str):
        """Choose which strategy the runs of ``user`` follow."""
        email = user if isinstance(user, str) else user.email
        updated = (DbUser.update(strategy=strategy)
                   .where(DbUser.email == email).execute())
        if not updated:
            raise DbException('user not found')

        # keep the cached profile in sync
        cached = _AUTH_CACHE.get(email)
        if cached is not None:
            credentials, expires, previous = cached
            _AUTH_CACHE[email] = (
                credentials, expires,
                User(email=previous.email, password=previous.password,
                     main_language=previous.main_language, level=previous.level,
                     target_language=previous.target_language,
                     strategy=strategy))

    def set_user_level(self, user, level: Optional[str]):
        email = user if isinstance(user, str) else user.email
        updated = (DbUser.update(level=level)
                   .where(DbUser.email == email).execute())
        if not updated:
            raise DbException('user not found')

        # keep the cached profile in sync
        cached = _AUTH_CACHE.get(email)
        if cached is not None:
            credentials, expires, previous = cached
            _AUTH_CACHE[email] = (
                credentials, expires,
                User(email=previous.email, password=previous.password,
                     main_language=previous.main_language, level=level,
                     target_language=previous.target_language,
                     strategy=previous.strategy))

    def set_user_target_language(self, user, target_language):
        email = user if isinstance(user, str) else user.email
        code = _code(target_language)
        updated = (DbUser.update(target_language=code)
                   .where(DbUser.email == email).execute())
        if not updated:
            raise DbException('user not found')

        cached = _AUTH_CACHE.get(email)
        if cached is not None:
            credentials, expires, previous = cached
            _AUTH_CACHE[email] = (
                credentials, expires,
                User(email=previous.email, password=previous.password,
                     main_language=previous.main_language,
                     level=previous.level,
                     target_language=Language.from_code(code),
                     strategy=previous.strategy))

    def list_users(self) -> List[Tuple[int, str]]:
        """All users as (id, email) pairs."""
        return [(db_user.id, db_user.email)
                for db_user in DbUser.select().order_by(DbUser.id)]

    def list_user_details(self) -> List[dict]:
        """All users with their profile (main language and level)."""
        details = []
        for db_user in DbUser.select().order_by(DbUser.id):
            main_language = None
            if db_user.main_language is not None:
                main_language = db_user.main_language.code
            details.append({
                'id': db_user.id,
                'email': db_user.email,
                'main_language': main_language,
                'level': db_user.level,
                'target_language': (db_user.target_language.code
                                    if db_user.target_language is not None
                                    else None),
            })
        return details

    def remove_user(self, email: str):
        """Delete a user together with their sessions and attempts."""
        db_user = DbUser.get_or_none(DbUser.email == email)
        if db_user is None:
            raise DbException('user not found')

        session_ids = [session.id
                       for session in DbSession.select().where(
                           DbSession.user == db_user)]

        if session_ids:
            (DbWordAttempt.delete()
             .where(DbWordAttempt.session.in_(session_ids)).execute())
            (DbVocabularySession.delete()
             .where(DbVocabularySession.session.in_(session_ids)).execute())
            (DbSession.delete()
             .where(DbSession.id.in_(session_ids)).execute())

        DbUser.delete().where(DbUser.id == db_user.id).execute()
        _AUTH_CACHE.pop(email, None)

    def update_user(self,
                    email: str,
                    main_language=None,
                    level: Optional[str] = None,
                    password: Optional[str] = None,
                    target_language=None,
                    strategy: Optional[str] = None):
        """Update the user profile. ``None`` means 'leave unchanged'."""
        update = {}
        if main_language is not None:
            update['main_language'] = DbLanguage.get(code=_code(main_language))
        if target_language is not None:
            update['target_language'] = DbLanguage.get(
                code=_code(target_language))
        if level is not None:
            update['level'] = level
        if password is not None:
            update['password'] = get_hashed_password(password)
        if strategy is not None:
            update['strategy'] = strategy

        if not update:
            raise DbException('nothing to update')

        updated = (DbUser.update(**update)
                   .where(DbUser.email == email).execute())
        if not updated:
            raise DbException('user not found')

        # the credentials / profile changed: drop the cached auth
        _AUTH_CACHE.pop(email, None)

    def _get_db_user(self, user: User) -> DbUser:
        return DbUser.get(email=user.email)

    # ---------------------------------------------------------- vocabularies
    @staticmethod
    def _pick_text(texts: Dict[str, str],
                   preferred: Optional[str]) -> Optional[str]:
        if not texts:
            return None
        if preferred is not None and preferred in texts:
            return texts[preferred]
        return next(iter(texts.values()))

    def _section_texts(self, voc_id: int) -> Dict[int, Dict[str, str]]:
        texts = defaultdict(dict)
        for section_text in (DbSectionText
                             .select(DbSectionText, DbSection, DbLanguage)
                             .join(DbSection)
                             .switch(DbSectionText)
                             .join(DbLanguage)
                             .where(DbSection.vocabulary == voc_id)):
            texts[section_text.section_id][section_text.language.code] = \
                section_text.text
        return texts

    def _load_vocabularies(self,
                           voc_ids,
                           input_code: str,
                           output_code: str,
                           display_code: str = None,
                           levels=None) -> Dict[int, Vocabulary]:
        """Load several vocabularies with a handful of queries (instead
        of four per vocabulary) and project them."""
        voc_ids = list(voc_ids)
        if not voc_ids:
            return {}

        display_code = display_code or input_code

        # plain SQL + raw rows: peewee's model/tuple hydration costs per
        # value and dominates the time for ~20k rows
        placeholders = ','.join('?' * len(voc_ids))

        words_by_vocabulary = defaultdict(list)
        for word_id, voc_id, section_id, word_type, level in db.execute_sql(
                'SELECT id, vocabulary_id, section_id, type, level '
                'FROM dbword WHERE vocabulary_id IN (%s) ORDER BY id'
                % placeholders, voc_ids).fetchall():
            words_by_vocabulary[voc_id].append(
                (word_id, section_id, word_type, level))

        texts_by_word = defaultdict(dict)
        for word_id, language_id, text, example in db.execute_sql(
                'SELECT t.word_id, t.language_id, t.text, t.example '
                'FROM dbwordtext t JOIN dbword w ON w.id = t.word_id '
                'WHERE w.vocabulary_id IN (%s)' % placeholders,
                voc_ids).fetchall():
            texts_by_word[word_id][language_id] = (text, example)

        section_texts = defaultdict(dict)
        for section_id, language_id, text in db.execute_sql(
                'SELECT st.section_id, st.language_id, st.text '
                'FROM dbsectiontext st '
                'JOIN dbsection s ON s.id = st.section_id '
                'WHERE s.vocabulary_id IN (%s)' % placeholders,
                voc_ids).fetchall():
            section_texts[section_id][language_id] = text

        titles = defaultdict(dict)
        for voc_id, language_id, title in db.execute_sql(
                'SELECT vocabulary_id, language_id, title '
                'FROM dbvocabularytitle WHERE vocabulary_id IN (%s)'
                % placeholders, voc_ids).fetchall():
            titles[voc_id][language_id] = title

        return {
            voc_id: self._project_vocabulary(
                voc_id,
                words_by_vocabulary.get(voc_id, []),
                texts_by_word, section_texts, titles.get(voc_id, {}),
                input_code, output_code, display_code, levels)
            for voc_id in voc_ids
        }

    @staticmethod
    def _project_vocabulary(voc_id, db_words, texts_by_word, section_texts,
                            titles, input_code, output_code, display_code,
                            levels) -> Vocabulary:
        words = []
        word_ids = {}
        sections = []
        section_ids = {}
        examples = {}
        input_examples = {}

        for word_id, section_id, word_type, level in db_words:
            word_texts = texts_by_word.get(word_id, {})
            in_text = word_texts.get(input_code)
            out_text = word_texts.get(output_code)

            if in_text is None or out_text is None:
                continue

            # words without a level are always kept
            if levels is not None and level is not None \
                    and level not in levels:
                continue

            word = Word(word_input=in_text[0], word_output=out_text[0],
                        type=word_type, level=level)
            words.append(word)
            word_ids[word] = word_id

            if section_id is not None:
                name = Database._pick_text(
                    section_texts.get(section_id, {}), display_code)
                sections.append(name)
                if name is not None:
                    section_ids[name] = section_id
            else:
                sections.append(None)

            if out_text[1] is not None:
                examples[word] = out_text[1]
            if in_text[1] is not None:
                input_examples[word] = in_text[1]

        title = Database._pick_text(titles, display_code)
        name = None if title is None else Word(word_input=title,
                                               word_output=title)

        voc = Vocabulary(name, words, input_code, output_code,
                         sections=sections, section_ids=section_ids)
        voc.set_id(voc_id)

        for word, word_id in word_ids.items():
            voc.set_word_id(word, word_id)
        for word, example in examples.items():
            voc.set_example(word, example)
        for word, example in input_examples.items():
            voc.set_input_example(word, example)

        return voc

    def _load_vocabulary(self,
                         voc_id: int,
                         input_code: str,
                         output_code: str,
                         display_code: str = None,
                         levels=None) -> Optional[Vocabulary]:
        """Project one vocabulary for the ``input_code -> output_code``
        direction, optionally restricted to the given levels."""
        return self._load_vocabularies([voc_id], input_code, output_code,
                                       display_code, levels).get(voc_id)

    def target_vocabulary_ids(self, input_code: str,
                              output_code: str) -> List[int]:
        in_text = DbWordText.alias()
        out_text = DbWordText.alias()

        rows = (DbWord
                .select(DbWord.vocabulary)
                .join(in_text, on=((in_text.word == DbWord.id) &
                                   (in_text.language == input_code)))
                .join(out_text, on=((out_text.word == DbWord.id) &
                                    (out_text.language == output_code)))
                .distinct())

        return [row.vocabulary_id for row in rows]

    def list_vocabularies(self, user: User,
                          target_language,
                          levels=None) -> Dict[int, Vocabulary]:
        input_code = None if user is None else _code(user.main_language)
        output_code = _code(target_language)

        if input_code is None or output_code is None:
            return {}

        voc_ids = self.target_vocabulary_ids(input_code, output_code)
        vocs = self._load_vocabularies(voc_ids, input_code, output_code,
                                       levels=levels)
        return {voc_id: voc for voc_id, voc in vocs.items() if len(voc) > 0}

    def get_vocabulary(self, user: User, voc_id: int,
                       target_language, levels=None) -> Optional[Vocabulary]:
        input_code = None if user is None else _code(user.main_language)
        output_code = _code(target_language)

        if input_code is None or output_code is None:
            return None

        return self._load_vocabulary(voc_id, input_code, output_code,
                                     levels=levels)

    def all_vocabulary_sizes(self) -> Dict[int, int]:
        sizes = defaultdict(int)
        for voc_id, in DbWord.select(DbWord.vocabulary).tuples():
            sizes[voc_id] += 1
        return dict(sizes)

    def vocabulary_summaries(self) -> List[dict]:
        titles = defaultdict(dict)
        for title in DbVocabularyTitle.select():
            titles[title.vocabulary_id][title.language.code] = title.title

        sizes = self.all_vocabulary_sizes()

        summaries = []
        for voc in DbVocabulary.select().order_by(DbVocabulary.id):
            summaries.append({
                'id': voc.id,
                'titles': titles.get(voc.id, {}),
                'size': sizes.get(voc.id, 0),
            })
        return summaries

    def word_attempts(self, voc_id: int) -> List[tuple]:
        """Practice attempts of a vocabulary, most recent first:
        (word id, success, typed word, timestamp of the guess)."""
        return [(attempt.word_id, attempt.success, attempt.typed_word,
                 attempt.time)
                for attempt in
                (DbWordAttempt
                 .select()
                 .join(DbWord)
                 .where(DbWord.vocabulary == voc_id)
                 .order_by(DbWordAttempt.time.desc(),
                           DbWordAttempt.id.desc()))]

    def list_word_texts(self, voc_id: int) -> Dict[int, Dict[str, dict]]:
        texts = defaultdict(dict)
        for text in (DbWordText
                     .select(DbWordText, DbWord)
                     .join(DbWord)
                     .where(DbWord.vocabulary == voc_id)):
            texts[text.word_id][text.language.code] = {
                'text': text.text,
                'example': text.example,
            }
        return dict(texts)

    def list_section_texts(self, voc_id: int) -> Dict[int, Dict[str, str]]:
        return self._section_texts(voc_id)

    def clear_vocabularies(self):
        """Remove every vocabulary (and the sessions/attempts which
        belong to them). Users and languages are kept."""
        DbWordAttempt.delete().execute()
        DbVocabularySession.delete().execute()
        DbSession.delete().execute()
        DbWordText.delete().execute()
        DbWord.delete().execute()
        DbSectionText.delete().execute()
        DbSection.delete().execute()
        DbVocabularyTitle.delete().execute()
        DbVocabulary.delete().execute()

    def import_changes(self, records, title_language: str = 'de') -> List[str]:
        """Preview of an ``--update`` import: the changes that would be
        applied to the database, one string per new vocabulary / new
        section / changed word. Words which would not change are left
        out. The database is not modified (matching is the same as
        ``import_vocabularies(..., replace=False)``)."""
        changes = []
        reported = set()

        vocabulary_ids = {}
        for voc_id, title in (DbVocabularyTitle
                              .select(DbVocabularyTitle.vocabulary_id,
                                      DbVocabularyTitle.title)
                              .where(DbVocabularyTitle.language ==
                                     title_language)
                              .tuples()):
            vocabulary_ids.setdefault(title, voc_id)
        title_by_id = {voc_id: title
                       for title, voc_id in vocabulary_ids.items()}

        section_ids = {}
        for section_id, text, voc_id in (DbSectionText
                                         .select(DbSectionText.section_id,
                                                 DbSectionText.text,
                                                 DbSection.vocabulary_id)
                                         .join(DbSection)
                                         .where(DbSectionText.language ==
                                                title_language)
                                         .tuples()):
            section_ids.setdefault((voc_id, text), section_id)
        section_name_by_id = {section: text
                              for (voc_id, text), section
                              in section_ids.items()}

        for record in records:
            name = record['vocabulary']
            section_name = record['section']
            voc_id = vocabulary_ids.get(name)
            if voc_id is None:
                section_id = None
            else:
                section_id = section_ids.get((voc_id, section_name))

            if voc_id is None:
                key = ('vocabulary', name)
                if key not in reported:
                    reported.add(key)
                    changes.append('add vocabulary "%s"' % name)
            elif section_name and section_id is None:
                key = ('section', voc_id, section_name)
                if key not in reported:
                    reported.add(key)
                    title = title_by_id.get(voc_id, voc_id)
                    changes.append('add section "%s" (%s)'
                                   % (section_name, title))

            texts = record['texts']
            examples = record['examples']
            main = texts.get(title_language) or \
                next(iter(texts.values()), '')

            word_id = record.get('id')
            db_word = None
            if word_id is not None:
                db_word = DbWord.get_or_none(DbWord.id == word_id)

            if db_word is None:
                detail = ', '.join('%s "%s"' % (lang, text)
                                   for lang, text in texts.items())
                if word_id is not None:
                    changes.append('add word %s: %s' % (word_id, detail))
                else:
                    changes.append('add word: %s' % detail)
                continue

            deltas = []
            if db_word.vocabulary_id != voc_id:
                old = title_by_id.get(db_word.vocabulary_id) or \
                    ('voc-id %s' % db_word.vocabulary_id)
                new = name or ('voc-id %s' % voc_id)
                deltas.append('vocabulary "%s" -> "%s"' % (old, new))
            if db_word.section_id != section_id:
                old_section = section_name_by_id.get(db_word.section_id)
                deltas.append('section "%s" -> "%s"'
                              % (old_section or '', section_name or ''))
            if db_word.type != record['type']:
                deltas.append('type %s -> %s'
                              % (db_word.type or '-', record['type'] or '-'))
            if db_word.level != record['level']:
                deltas.append('level %s -> %s'
                              % (db_word.level or '-', record['level'] or '-'))

            for language, text in texts.items():
                word_text = DbWordText.get_or_none(
                    (DbWordText.word == db_word.id) &
                    (DbWordText.language == language))
                if word_text is None:
                    deltas.append('%s text "%s" (new)'
                                  % (language, text))
                    continue
                if word_text.text != text:
                    deltas.append('%s text "%s" -> "%s"'
                                  % (language, word_text.text, text))
                example = examples.get(language)
                if word_text.example != example:
                    deltas.append('%s example "%s" -> "%s"'
                                  % (language, word_text.example or '',
                                     example or ''))

            if deltas:
                changes.append('word %s (%s): %s'
                               % (word_id, main, '; '.join(deltas)))

        return changes

    def import_vocabularies(self, records, title_language: str = 'de',
                            replace: bool = True) -> int:
        """Create or update vocabularies from ``records``.

        Each record is a dict with ``id`` (optional, stable word id),
        ``vocabulary``, ``section``, ``type``, ``level``, ``texts``
        ({language: text}) and ``examples`` ({language: sentence}).

        With ``replace`` the existing vocabularies are removed first.
        Without it, words are matched by their id and updated, so their
        ids and practice history are preserved.
        """
        if replace:
            self.clear_vocabularies()

        # vocabularies / sections are matched by their name
        vocabulary_ids = {}
        for voc_id, title in (DbVocabularyTitle
                              .select(DbVocabularyTitle.vocabulary_id,
                                      DbVocabularyTitle.title)
                              .where(DbVocabularyTitle.language ==
                                     title_language)
                              .tuples()):
            vocabulary_ids.setdefault(title, voc_id)

        section_ids = {}
        for section_id, text, voc_id in (DbSectionText
                                         .select(DbSectionText.section_id,
                                                 DbSectionText.text,
                                                 DbSection.vocabulary_id)
                                         .join(DbSection)
                                         .where(DbSectionText.language ==
                                                title_language)
                                         .tuples()):
            section_ids.setdefault((voc_id, text), section_id)

        used_vocabularies = set()

        for record in records:
            name = record['vocabulary']

            voc_id = vocabulary_ids.get(name)
            if voc_id is None:
                voc_id = DbVocabulary.create().id
                vocabulary_ids[name] = voc_id
                if name:
                    DbVocabularyTitle.create(vocabulary=voc_id,
                                             language=title_language,
                                             title=name)
            used_vocabularies.add(voc_id)

            section_name = record['section']
            key = (voc_id, section_name)
            if key not in section_ids:
                if section_name:
                    section = DbSection.create(vocabulary=voc_id)
                    DbSectionText.create(section=section,
                                         language=title_language,
                                         text=section_name)
                    section_ids[key] = section.id
                else:
                    section_ids[key] = None

            word_id = record.get('id')
            db_word = None
            if word_id is not None:
                db_word = DbWord.get_or_none(DbWord.id == word_id)

            if db_word is None:
                values = {
                    'vocabulary': voc_id,
                    'section': section_ids[key],
                    'type': record['type'],
                    'level': record['level'],
                }
                if word_id is not None:
                    values['id'] = word_id
                db_word = DbWord.create(**values)
            else:
                db_word.vocabulary = voc_id
                db_word.section = section_ids[key]
                db_word.type = record['type']
                db_word.level = record['level']
                db_word.save()

            for language, text in record['texts'].items():
                example = record['examples'].get(language)
                word_text = DbWordText.get_or_none(
                    (DbWordText.word == db_word.id) &
                    (DbWordText.language == language))
                if word_text is None:
                    DbWordText.create(word=db_word.id,
                                      language=language,
                                      text=text,
                                      example=example)
                else:
                    word_text.text = text
                    word_text.example = example
                    word_text.save()

        return len(used_vocabularies)

    def create_vocabulary(self, voc: Vocabulary) -> int:
        input_code = voc.input_language
        output_code = voc.output_language

        new_voc = DbVocabulary.create()

        # vocabulary title(s)
        if voc.name is not None:
            DbVocabularyTitle.create(vocabulary=new_voc,
                                     language=output_code,
                                     title=voc.name.word_output)
            if voc.name.word_input != voc.name.word_output:
                DbVocabularyTitle.create(vocabulary=new_voc,
                                         language=input_code,
                                         title=voc.name.word_input)

        # sections
        section_by_name = {}
        for name in voc.word_sections:
            if name is None or name in section_by_name:
                continue
            db_section = DbSection.create(vocabulary=new_voc)
            DbSectionText.create(section=db_section,
                                 language=output_code,
                                 text=name)
            section_by_name[name] = db_section

        # words and their texts
        for word, section_name in zip(voc.words, voc.word_sections):
            db_word = DbWord.create(vocabulary=new_voc,
                                    section=section_by_name.get(section_name),
                                    type=word.type,
                                    level=word.level)
            DbWordText.create(word=db_word,
                              language=input_code,
                              text=word.word_input,
                              example=voc.input_example(word))
            DbWordText.create(word=db_word,
                              language=output_code,
                              text=word.word_output,
                              example=voc.example(word))

        voc.set_id(new_voc.id)
        return new_voc.id

    def add_word(self, voc_id: int, input_code: str, output_code: str,
                 word: Word) -> int:
        db_voc = DbVocabulary.get(voc_id)

        db_word = DbWord.create(vocabulary=db_voc, type=word.type,
                                level=word.level)

        DbWordText.create(word=db_word, language=input_code,
                          text=word.word_input)
        DbWordText.create(word=db_word, language=output_code,
                          text=word.word_output)

        return db_word.id

    def update_word_type(self, word_id: int, word_type: Optional[str]):
        (DbWord.update(type=word_type)
         .where(DbWord.id == word_id).execute())

    def update_word_level(self, word_id: int, level: Optional[str]):
        (DbWord.update(level=level)
         .where(DbWord.id == word_id).execute())

    def update_word_text(self, word_id: int, language,
                         text: str = None, example: str = None):
        update = {}
        if text is not None:
            update['text'] = text
        if example is not None:
            update['example'] = example
        if not update:
            return

        (DbWordText
         .update(**update)
         .where((DbWordText.word == word_id) &
                (DbWordText.language == _code(language)))
         .execute())

    def remove_vocabulary(self, voc):
        voc_id = voc.id if isinstance(voc, Vocabulary) else voc

        word_ids = [db_word.id
                    for db_word in DbWord.select().where(
                        DbWord.vocabulary == voc_id)]
        section_ids = [db_section.id
                       for db_section in DbSection.select().where(
                           DbSection.vocabulary == voc_id)]

        if word_ids:
            (DbWordAttempt.delete()
             .where(DbWordAttempt.word.in_(word_ids)).execute())

        # sessions reference words (current_word) and sections, so they
        # have to go first
        vocabulary_sessions = list(DbVocabularySession
                                   .select()
                                   .where(DbVocabularySession.vocabulary ==
                                          voc_id))
        if vocabulary_sessions:
            (DbVocabularySession.delete()
             .where(DbVocabularySession.vocabulary == voc_id).execute())
            session_ids = [vs.session_id for vs in vocabulary_sessions]
            (DbSession.delete()
             .where(DbSession.id.in_(session_ids)).execute())

        if word_ids:
            DbWordText.delete().where(DbWordText.word.in_(word_ids)).execute()
        DbWord.delete().where(DbWord.vocabulary == voc_id).execute()

        if section_ids:
            (DbSectionText.delete()
             .where(DbSectionText.section.in_(section_ids)).execute())
        DbSection.delete().where(DbSection.vocabulary == voc_id).execute()

        (DbVocabularyTitle.delete()
         .where(DbVocabularyTitle.vocabulary == voc_id).execute())
        DbVocabulary.delete().where(DbVocabulary.id == voc_id).execute()

    # ------------------------------------------------------------- sessions
    def create_new_session(self,
                           user: User,
                           voc: Vocabulary,
                           section: Optional[str] = None,
                           level: Optional[str] = None) -> Session:
        scope_voc = voc
        section_id = None

        if section is not None:
            section_id = voc.section_id(section)
            section_voc = voc.section(section)
            if section_voc is None:
                raise DbException(f'section not found: {section}')
            scope_voc = section_voc

        db_user = self._get_db_user(user)
        new_session = Session([], scope_voc,
                              strategy=make_strategy(user.strategy))

        new_db_session = DbSession.create(user=db_user.id,
                                          creation=datetime.now(),
                                          finished=len(scope_voc) == 0)
        new_session.set_id(new_db_session.id)
        DbVocabularySession.create(session=new_db_session,
                                   vocabulary=scope_voc.id,
                                   input_language=voc.input_language,
                                   output_language=voc.output_language,
                                   section=section_id,
                                   level=level)

        db_session = DbSession.get(new_db_session.id)
        current_db_word = None
        if new_session.current_word is not None:
            current_db_word = self._get_db_word(new_session,
                                                new_session.current_word)
        db_session.current_word = current_db_word
        db_session.save()

        return new_session

    def _get_db_word(self,
                     session: Session,
                     word: Word) -> Optional[DbWord]:
        db_voc_session = (DbVocabularySession
                          .select()
                          .where(DbVocabularySession.session == session.id)
                          .first())

        in_text = DbWordText.alias()
        out_text = DbWordText.alias()

        query = (DbWord
                 .select(DbWord)
                 .join(in_text,
                       on=((in_text.word == DbWord.id) &
                           (in_text.language ==
                            db_voc_session.input_language_id)))
                 .join(out_text,
                       on=((out_text.word == DbWord.id) &
                           (out_text.language ==
                            db_voc_session.output_language_id)))
                 .where(DbWord.vocabulary == db_voc_session.vocabulary_id)
                 .where(in_text.text == word.word_input)
                 .where(out_text.text == word.word_output))

        if db_voc_session.section_id is not None:
            query = query.where(DbWord.section == db_voc_session.section_id)

        for row in query:
            return row

        assert False
        return None

    def add_word_attempt(self,
                         session: Session,
                         word_attempt: WordAttempt):
        session_id = session.id

        db_session = DbSession.get(session_id)

        if session.current_word is None:
            db_session.current_word = None
        else:
            db_session.current_word = self._get_db_word(
                session, session.current_word)

        db_session.finished = session.is_finished
        db_session.save()

        db_word = self._get_db_word(session, word_attempt.word)

        DbWordAttempt.create(word=db_word.id,
                             typed_word=word_attempt.typed_word,
                             session=session_id,
                             time=word_attempt.time,
                             success=word_attempt.success)

    def last_session(self,
                     user: User,
                     voc: Vocabulary,
                     finished: bool = None,
                     section: Optional[str] = None) -> Optional[Session]:
        db_user = self._get_db_user(user)

        if voc.id is None:
            return None

        sessions = (DbSession
                    .select()
                    .join(DbVocabularySession)
                    .where(DbSession.user == db_user)
                    .where(DbVocabularySession.vocabulary == voc.id)
                    .where(DbVocabularySession.input_language ==
                           voc.input_language)
                    .where(DbVocabularySession.output_language ==
                           voc.output_language))

        if section == '':
            # '' means: sessions whose scope is the whole vocabulary
            sessions = sessions.where(DbVocabularySession.section.is_null())
        elif section is not None:
            section_id = voc.section_id(section)
            if section_id is None:
                return None
            sessions = sessions.where(DbVocabularySession.section ==
                                      section_id)

        if finished is not None:
            sessions = sessions.where(DbSession.finished == finished)

        sessions = sessions.order_by(DbSession.id.desc())
        sessions = list(sessions)

        if not sessions:
            return None

        return self.load_session(sessions[0].id)

    def load_session(self, session_id: int) -> Session:
        db_session = DbSession.get(session_id)

        db_voc_session = (DbVocabularySession
                          .select()
                          .where(DbVocabularySession.session == session_id)
                          .first())

        if db_voc_session is None:
            ret = Session([], Vocabulary(None, []))
            ret.set_id(session_id)
            return ret

        input_code = db_voc_session.input_language.code
        output_code = db_voc_session.output_language.code
        levels = included_levels(db_voc_session.level)

        v = self._load_vocabulary(db_voc_session.vocabulary_id,
                                  input_code, output_code,
                                  levels=levels)

        if db_voc_session.section_id is not None:
            section_voc = v.section_by_id(db_voc_session.section_id)
            if section_voc is not None:
                v = section_voc

        strategy = make_strategy(db_session.user.strategy)

        attempts = []

        for attempt in (DbWordAttempt
                        .select()
                        .where(DbWordAttempt.session == session_id)
                        .order_by(DbWordAttempt.id.asc())):

            word = v.word(attempt.word_id)
            if word is None:
                continue

            attempts.append(WordAttempt(word=word,
                                        typed_word=attempt.typed_word,
                                        success=attempt.success,
                                        time=attempt.time,
                                        example=v.example(word),
                                        input_example=v.input_example(word)))

        current_word = None
        if db_session.current_word is not None:
            current_word = v.word(db_session.current_word_id)

        ret = Session(attempts, v, current_word=current_word,
                      strategy=strategy)
        ret.set_id(session_id)
        return ret

    # --------------------------------------------------------------- stats
    def vocabulary_stats(self, voc: Vocabulary,
                         user: Optional[User] = None) -> Optional[VocabularyStats]:
        """Error probability per word of ``voc``, from the attempts of one
        ``user``. Without a user, every user's attempts would be mixed
        together, so the page always passes the current user."""
        success_by_word_id = defaultdict(int)
        error_by_word_id = defaultdict(int)

        query = (DbWordAttempt
                 .select()
                 .join(DbWord)
                 .where(DbWord.vocabulary == voc.id))

        if user is not None:
            db_user = self._get_db_user(user)
            query = (query
                     .switch(DbWordAttempt)
                     .join(DbSession)
                     .where(DbSession.user == db_user))

        for attempt in query:
            if attempt.success:
                success_by_word_id[attempt.word_id] += 1
            else:
                error_by_word_id[attempt.word_id] += 1

        ret = {}

        for word_id in set(success_by_word_id) | set(error_by_word_id):
            word = voc.word(word_id)
            if word is None:
                continue

            success = success_by_word_id[word_id]
            error = error_by_word_id[word_id]

            ret[word] = error / (error + success) * 100

        return VocabularyStats(voc, ret)

    def known_word_counts(self, user: User,
                          levels=None) -> Dict[int, int]:
        """Vocabulary id -> number of distinct words ``user`` has mastered:
        guessed correctly during a completed run (a single successful guess
        in a session which was left unfinished does not count)."""
        db_user = self._get_db_user(user)
        counts = defaultdict(int)
        seen = set()

        query = (DbWordAttempt
                 .select(DbWordAttempt.word_id, DbWord.vocabulary_id)
                 .join(DbWord)
                 .switch(DbWordAttempt)
                 .join(DbSession)
                 .where(DbSession.user == db_user)
                 .where(DbSession.finished == True)
                 .where(DbWordAttempt.success == True))

        if levels is not None:
            query = query.where((DbWord.level.in_(list(levels))) |
                                DbWord.level.is_null())

        for word_id, vocabulary_id in query.tuples():
            if word_id in seen:
                continue
            seen.add(word_id)
            counts[vocabulary_id] += 1

        return dict(counts)

    def known_word_counts_by_user(self) -> Dict[int, Dict[int, int]]:
        """User id -> (vocabulary id -> words mastered in a completed run)."""
        known = defaultdict(lambda: defaultdict(int))
        seen = set()

        rows = (DbWordAttempt
                .select(DbWordAttempt.word_id, DbWord.vocabulary_id,
                        DbSession.user_id)
                .join(DbWord)
                .switch(DbWordAttempt)
                .join(DbSession)
                .where(DbSession.finished == True)
                .where(DbWordAttempt.success == True)
                .tuples())

        for word_id, vocabulary_id, user_id in rows:
            key = (user_id, word_id)
            if key in seen:
                continue
            seen.add(key)
            known[user_id][vocabulary_id] += 1

        return {user_id: dict(counts)
                for user_id, counts in known.items()}


# --------------------------------------------------------------- migration

NEW_TABLES = [DbLanguage, DbUser, DbVocabulary, DbVocabularyTitle,
              DbSection, DbSectionText, DbWord, DbWordText,
              DbSession, DbVocabularySession, DbWordAttempt]


def _table_columns(table: str) -> List[str]:
    cursor = db.execute_sql('PRAGMA table_info(%s)' % table)
    return [row[1] for row in cursor.fetchall()]


def _legacy_database() -> bool:
    return 'word_input' in _table_columns('dbword')


def _migrate_legacy():
    """Turn the old (language pair based) schema into the language
    agnostic one, preserving ids so that attempts keep working."""
    db.execute_sql('PRAGMA foreign_keys = OFF')

    users = db.execute_sql(
        'SELECT id, email, password FROM dbuser').fetchall()

    main_languages = {}
    try:
        for user_id, language_id in db.execute_sql(
                'SELECT user_id, language_id FROM dbspeak').fetchall():
            main_languages.setdefault(user_id, language_id)
    except Exception:
        pass

    words = db.execute_sql(
        'SELECT id, vocabulary_id, word_input, word_output, section '
        'FROM dbword').fetchall()
    vocabularies = db.execute_sql(
        'SELECT id, input_language_id, output_language_id, name '
        'FROM dbvocabulary').fetchall()
    vocabulary_sessions = db.execute_sql(
        'SELECT id, session_id, vocabulary_id, flipped, section '
        'FROM dbvocabularysession').fetchall()

    # note: dbuser is rebuilt too (instead of ALTER TABLE) to avoid a
    # peewee/sqlite quirk when updating a freshly added column
    for table in ('dbspeak', 'dbvocabularysession', 'dbword',
                  'dbvocabulary', 'dbuser'):
        db.execute_sql('DROP TABLE IF EXISTS %s' % table)

    db.create_tables(NEW_TABLES)

    with db.atomic():
        for user_id, email, password in users:
            db.execute_sql(
                'INSERT INTO dbuser (id, email, password, main_language_id) '
                'VALUES (?, ?, ?, ?)',
                (user_id, email, password, main_languages.get(user_id)))

        _migrate_legacy_vocabularies(vocabularies, words, vocabulary_sessions)

    db.execute_sql('PRAGMA foreign_keys = ON')


def _migrate_legacy_vocabularies(vocabularies, words, vocabulary_sessions):
    vocabulary_languages = {v[0]: (v[1], v[2]) for v in vocabularies}

    for voc_id, input_code, output_code, name in vocabularies:
        db.execute_sql('INSERT INTO dbvocabulary (id) VALUES (?)', (voc_id,))

        if name:
            db.execute_sql(
                'INSERT INTO dbvocabularytitle (vocabulary_id, language_id, '
                'title) VALUES (?, ?, ?)', (voc_id, output_code, name))

    # (vocabulary id, section text) -> section id
    section_ids = {}

    for word_id, voc_id, word_input, word_output, section in words:
        input_code, output_code = vocabulary_languages[voc_id]

        section_id = None
        if section:
            key = (voc_id, section)
            if key not in section_ids:
                cursor = db.execute_sql(
                    'INSERT INTO dbsection (vocabulary_id) VALUES (?)',
                    (voc_id,))
                section_id = cursor.lastrowid
                db.execute_sql(
                    'INSERT INTO dbsectiontext (section_id, language_id, '
                    'text) VALUES (?, ?, ?)',
                    (section_id, output_code, section))
                section_ids[key] = section_id
            else:
                section_id = section_ids[key]

        db.execute_sql(
            'INSERT INTO dbword (id, vocabulary_id, section_id, level) '
            'VALUES (?, ?, ?, ?)', (word_id, voc_id, section_id, 'B1'))
        db.execute_sql(
            'INSERT INTO dbwordtext (word_id, language_id, text) '
            'VALUES (?, ?, ?)', (word_id, input_code, word_input))
        db.execute_sql(
            'INSERT INTO dbwordtext (word_id, language_id, text) '
            'VALUES (?, ?, ?)', (word_id, output_code, word_output))

    for vs_id, session_id, voc_id, flipped, section in vocabulary_sessions:
        input_code, output_code = vocabulary_languages[voc_id]
        if flipped:
            input_code, output_code = output_code, input_code

        section_id = section_ids.get((voc_id, section)) if section else None

        db.execute_sql(
            'INSERT INTO dbvocabularysession (id, session_id, vocabulary_id, '
            'input_language_id, output_language_id, section_id) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (vs_id, session_id, voc_id, input_code, output_code, section_id))


def _add_column_if_missing(table: str, column: str, definition: str) -> bool:
    if column in _table_columns(table):
        return False
    db.execute_sql('ALTER TABLE %s ADD COLUMN %s %s'
                   % (table, column, definition))
    return True


def _add_level_column() -> bool:
    if 'level' in _table_columns('dbword'):
        return False
    db.execute_sql('ALTER TABLE dbword ADD COLUMN level varchar(255)')
    # words which existed before levels were introduced are B1
    db.execute_sql("UPDATE dbword SET level = 'B1'")
    return True


def _remap_old_levels():
    """A2 is no longer a level: keep those words/learners at B1."""
    db.execute_sql("UPDATE dbword SET level = 'B1' WHERE level = 'A2'")
    db.execute_sql("UPDATE dbuser SET level = 'B1' WHERE level = 'A2'")


def load_database(name: str) -> Database:
    db.init(name)
    db.connect()
    _AUTH_CACHE.clear()
    db.execute_sql('PRAGMA foreign_keys = OFF')

    if _legacy_database():
        _migrate_legacy()
    else:
        db.create_tables(NEW_TABLES)
        # columns added after the first releases
        migrated = False
        migrated |= _add_column_if_missing('dbword', 'type', 'varchar(255)')
        migrated |= _add_column_if_missing('dbwordattempt', 'time',
                                           'datetime')
        migrated |= _add_level_column()
        migrated |= _add_column_if_missing('dbuser', 'level', 'varchar(255)')
        migrated |= _add_column_if_missing('dbuser', 'target_language_id',
                                           'varchar(255)')
        migrated |= _add_column_if_missing('dbuser', 'strategy',
                                           'varchar(255)')
        migrated |= _add_column_if_missing('dbvocabularysession', 'level',
                                           'varchar(255)')
        _remap_old_levels()

        if migrated:
            # adding a column can leave an index on the new column
            # inconsistent (sqlite/peewee): rebuild the indexes
            db.execute_sql('REINDEX')

    db.execute_sql('PRAGMA foreign_keys = ON')

    return Database()

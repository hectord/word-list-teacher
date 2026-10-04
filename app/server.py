# -*- coding: utf-8 -*-

import os
from typing import Optional, List
from pathlib import Path

from fastapi import (FastAPI, Form, Request, Response, Depends,
                     HTTPException, status)
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from starlette.responses import RedirectResponse
from pydantic import BaseModel

from optimizer import VocabularySelector

from learn import Vocabulary, Session, Word, Language, User
from learn import LEVELS, STRATEGIES, included_levels
from store import load_database, DbException


BASE_PATH = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_PATH / "templates"))

DATADIR = Path(os.environ.get('DATADIR', BASE_PATH))

VOCABULARIES = DATADIR / 'learn.db'
db = load_database(VOCABULARIES)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
security = HTTPBasic()


class WordInput(BaseModel):
    word_id: int
    word: str


class WordOutput(BaseModel):
    word: str
    session_id: int
    word_id: int


class WordResult(BaseModel):
    success: bool

    word_input: WordInput
    word_output: WordOutput

    hint: Optional[str]

    # a sentence using the answer word (in the answer's language)
    example: Optional[str] = None

    # the same sentence translated into the learner's own language
    # (the session's input language), when available
    input_example: Optional[str] = None

    # if None => no more word
    next_word: Optional[WordInput]

    # end-of-run statistics, present when the session just finished
    summary: Optional[dict] = None


def get_user(creds: HTTPBasicCredentials = Depends(security)) -> User:
    username = creds.username
    password = creds.password

    try:
        user = db.get_user(username, password)
    except DbException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )

    return user


def _target_languages(user: User) -> List[Language]:
    if user.main_language is None:
        return []
    return db.target_languages(user.main_language.code)


def _resolve_target(user: User,
                    voc_id: Optional[int] = None,
                    to: Optional[str] = None) -> Optional[Language]:
    """Pick the language the user practises (B), defaulting to the first
    available one."""
    targets = _target_languages(user)

    if to is not None:
        language = Language.from_code(to)
        if language in targets:
            return language

    if user.target_language is not None and user.target_language in targets:
        return user.target_language

    if voc_id is None or user.main_language is None:
        return targets[0] if targets else None

    for language in targets:
        supported = db.target_vocabulary_ids(user.main_language.code,
                                             language.code)
        if voc_id in supported:
            return language

    return targets[0] if targets else None


@app.get("/")
def root():
    return RedirectResponse(url='/index')


@app.get("/logout")
def logout():
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or password",
        headers={"WWW-Authenticate": "Basic"},
    )


@app.get("/settings")
async def settings(request: Request,
                   user: User = Depends(get_user)):
    return TEMPLATES.TemplateResponse(
        request, "settings.html",
        {
            'user': user,
            'strategies': STRATEGIES,
        },
        headers={'Cache-Control': 'no-store'}
    )


@app.post("/settings")
async def save_settings(request: Request,
                        strategy: str = Form(...),
                        unlimited: Optional[str] = Form(None),
                        words_per_run: Optional[int] = Form(None),
                        user: User = Depends(get_user)):

    if strategy not in STRATEGIES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="unknown strategy")

    db.set_user_strategy(user, strategy)

    if unlimited == 'on':
        # the whole vocabulary in each run
        db.set_user_words_per_run(user, 0)
    elif words_per_run is not None:
        if words_per_run <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="words_per_run must be positive")
        db.set_user_words_per_run(user, words_per_run)

    # 303 (instead of the 307 default): the browser must re-send the
    # form as a GET, otherwise it would re-POST here and loop forever
    return RedirectResponse(url='/index', status_code=303)


@app.get("/vocabulary")
async def vocabulary(request: Request,
                     id: int,
                     to: Optional[str] = None,
                     user: User = Depends(get_user)):

    target = _resolve_target(user, voc_id=id, to=to)
    levels = included_levels(user.level)
    voc = db.get_vocabulary(user, id, target, levels=levels)

    if voc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="vocabulary not found")

    stats = db.vocabulary_stats(voc, user)

    word_count = len(voc.words)
    unknown_count = sum(
        1 for word in voc.words if stats.errors_prob_for(word) > 40.0)

    sections = []
    for section in voc.sections:
        resume_session = db.last_session(user, voc, section=section.name)
        resume = None
        if resume_session is not None and not resume_session.is_finished:
            resume = resume_session
        sections.append({
            'name': section.name,
            'size': len(section.vocabulary),
            'resume': resume,
        })

    whole_session = db.last_session(user, voc, section='')
    unfinished_session = None
    if whole_session is not None and not whole_session.is_finished:
        unfinished_session = whole_session

    sections_by_index = list(voc.word_sections)

    return TEMPLATES.TemplateResponse(
        request, "vocabulary.html",
        {
            'user': user,
            'voc': voc,
            'stats': stats,
            'voc_id': id,
            'target': target,
            'word_count': word_count,
            'unknown_count': unknown_count,
            'sections': sections,
            'sections_by_index': sections_by_index,
            'unfinished_session': unfinished_session
        },
        headers={'Cache-Control': 'no-store'}
    )


@app.get("/index")
async def index(request: Request,
                to: Optional[str] = None,
                level: Optional[str] = None,
                user: User = Depends(get_user)):

    targets = _target_languages(user)
    target = _resolve_target(user, to=to)

    # the target language lives in the user profile too; picking one saves it
    if to is not None:
        requested = Language.from_code(to)
        if requested in targets and requested != user.target_language:
            db.set_user_target_language(user, requested)

    # the level lives in the user profile; selecting one saves it
    selected_level = user.level
    if level is not None and level in LEVELS:
        if level != user.level:
            db.set_user_level(user, level)
        selected_level = level

    levels = included_levels(selected_level)

    vocabularies = db.list_vocabularies(user, target, levels=levels)
    session_by_vocabulary = {}
    has_finished_session = {}
    known_by_vocabulary = {}
    known_percentage_by_vocabulary = {}
    known_counts = db.known_word_counts(user, levels)
    total_words = 0
    total_known = 0
    entries = []

    for voc_id, vocabulary in vocabularies.items():
        session = db.last_session(user, vocabulary)
        if session is not None and not session.is_finished:
            session_by_vocabulary[vocabulary] = session

        finished_session = db.last_session(user, vocabulary, finished=True)
        has_finished_session[vocabulary] = finished_session is not None

        size = len(vocabulary)
        known = known_counts.get(voc_id, 0)
        known_by_vocabulary[vocabulary] = known
        known_percentage_by_vocabulary[vocabulary] = \
            (100 * known // size) if size else 0
        total_words += size
        total_known += known
        entries.append((voc_id, vocabulary))

    # practised vocabularies first, the weakest (least known) on top;
    # vocabularies never practised come last
    def sort_key(entry):
        vocabulary = entry[1]
        practised = (has_finished_session.get(vocabulary, False) or
                     vocabulary in session_by_vocabulary)
        return (
            0 if practised else 1,
            known_percentage_by_vocabulary.get(vocabulary, 0),
            entry[0],
        )

    entries.sort(key=sort_key)

    known_percentage = \
        (100 * total_known // total_words) if total_words else 0

    return TEMPLATES.TemplateResponse(
        request, "index.html",
        {
            'user': user,
            'language': user.main_language,
            'targets': targets,
            'target': target,
            'levels': LEVELS,
            'selected_level': selected_level,
            'vocabularies': entries,
            'session_by_vocabulary': session_by_vocabulary,
            'has_finished_session': has_finished_session,
            'known_by_vocabulary': known_by_vocabulary,
            'known_percentage_by_vocabulary': known_percentage_by_vocabulary,
            'total_words': total_words,
            'total_known': total_known,
            'known_percentage': known_percentage,
        },
        headers={'Cache-Control': 'no-store'}
    )


@app.get("/scoreboard")
async def scoreboard(request: Request,
                     user: User = Depends(get_user)):

    sizes = db.all_vocabulary_sizes()
    total_words = sum(sizes.values())

    known_by_user = db.known_word_counts_by_user()

    entries = []
    for user_id, email in db.list_users():
        per_vocabulary = known_by_user.get(user_id, {})
        known = sum(per_vocabulary.get(voc_id, 0) for voc_id in sizes)
        percentage = (100 * known // total_words) if total_words else 0
        entries.append({
            'email': email,
            'known': known,
            'total': total_words,
            'percentage': percentage,
            'is_me': email == user.email,
        })

    entries.sort(key=lambda e: (e['percentage'], e['known']),
                 reverse=True)

    # bars are relative to the best user so they are readable at any scale
    best = entries[0]['known'] if entries else 0
    for entry in entries:
        entry['bar_percentage'] = \
            (100 * entry['known'] // best) if best else 0

    return TEMPLATES.TemplateResponse(
        request, "scoreboard.html",
        {
            'user': user,
            'entries': entries,
            'total_words': total_words,
        },
        headers={'Cache-Control': 'no-store'}
    )


@app.get("/new_session")
async def new_session(request: Request,
                      voc_id: int,
                      to: Optional[str] = None,
                      section: Optional[str] = None,
                      user: User = Depends(get_user)):

    target = _resolve_target(user, voc_id=voc_id, to=to)
    levels = included_levels(user.level)
    voc = db.get_vocabulary(user, voc_id, target, levels=levels)

    if voc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="vocabulary not found")

    try:
        session = db.create_new_session(user, voc, section=section,
                                        level=user.level)
    except DbException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="section not found",
        )

    return RedirectResponse(url=f'/learn?session_id={session.id}')


def _session_summary(session: Session, user: User) -> Optional[dict]:
    """End-of-run statistics (numbers only). For the AI strategy the
    understanding model statistics are added."""
    if not session.is_finished:
        return None

    understand = None
    if session.strategy_name == 'ai':
        history = db.historical_attempts(user, session.vocabulary.id)
        selector = VocabularySelector(history)
        understand = {
            word.id: selector.understanding(word.id)
            for word in session.run.words
        }

    return session.summary(understand)


@app.get("/learn")
async def learn(request: Request,
                response: Response,
                session_id: int,
                user: User = Depends(get_user)):
    session = db.load_session(session_id)

    first_word = None
    if session.current_word is not None:
        current_word = session.current_word
        vocabulary = session.vocabulary
        first_word = WordInput(word=current_word.word_input,
                               word_id=vocabulary.word_id(current_word))

    ret = TEMPLATES.TemplateResponse(
        request, "learn.html",
        {
            'session': session,
            'first_word': first_word,
            'summary': _session_summary(session, user),
        },
        headers={'Cache-Control': 'no-store'}
    )

    return ret


@app.post("/word")
async def post_word(word_output: WordOutput,
                    user: User = Depends(get_user)):
    session = db.load_session(word_output.session_id)
    vocabulary = session.vocabulary

    current_word = vocabulary.word(word_output.word_id)
    hint_word = current_word.word_output
    example = vocabulary.example(current_word)
    input_example = vocabulary.input_example(current_word)

    result = session.guess(current_word, word_output.word)

    success = False
    if result is not None:
        db.add_word_attempt(session, result)
        success = result.success

    next_word_input = None
    if session.current_word is not None:
        next_word = session.current_word
        next_word_input = WordInput(word=next_word.word_input,
                                    word_id=vocabulary.word_id(next_word))

    return WordResult(success=success,
                      hint=hint_word,
                      example=example,
                      input_example=input_example,
                      word_input=WordInput(word=current_word.word_input,
                                           word_id=word_output.word_id),
                      word_output=word_output,
                      next_word=next_word_input,
                      summary=_session_summary(session, user))

# -*- coding: utf-8 -*-

import os
from typing import Optional
from pathlib import Path
import secrets
from collections import defaultdict

from fastapi import FastAPI, Request, Response, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from starlette.responses import RedirectResponse
from pydantic import BaseModel

from learn import Vocabulary, Session, Word, Language, User
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

    # if None => no more word
    next_word: Optional[WordInput]


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


@app.get("/")
def root():
    return RedirectResponse(url='/index')

@app.get("/logout")
def root():
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or password",
        headers={"WWW-Authenticate": "Basic"},
    )


@app.get("/vocabulary")
async def index(request: Request,
                id: int,
                user: User = Depends(get_user)):

    voc = db.get_vocabulary(user, id)
    stats = db.vocabulary_stats(voc)

    return TEMPLATES.TemplateResponse(
        "vocabulary.html",
        {
            'request': request,
            'voc': voc,
            'stats': stats
        },
    )

@app.get("/index")
async def index(request: Request, user: User = Depends(get_user)):
    vocabularies = db.list_vocabularies(user)
    session_by_vocabulary = {}
    percentage_by_vocabulary = {}
    vocabularies_by_languages = defaultdict(list)

    for voc_id, vocabulary in vocabularies.items():
        input_language = Language.from_code(vocabulary.input_language)
        output_language = Language.from_code(vocabulary.output_language)

        inout = (input_language, output_language)

        session = db.last_session(user, vocabulary)
        if session is not None and not session.is_finished:
            session_by_vocabulary[vocabulary] = session

        finished_session = db.last_session(user, vocabulary,
                                           finished=True)
        percentage_by_vocabulary[vocabulary] = 0.0
        if finished_session:
            percentage_by_vocabulary[vocabulary] = finished_session.accuracy

        vocabularies_by_languages[inout].append((voc_id, vocabulary))

    for vocabularies in vocabularies_by_languages.values():
        vocabularies.sort(key=lambda e: percentage_by_vocabulary.get(e[1], 0.0))

    return TEMPLATES.TemplateResponse(
        "index.html",
        {
            'request': request,
            'vocabularies_by_languages': vocabularies_by_languages,
            'session_by_vocabulary': session_by_vocabulary,
            'percentage_by_vocabulary': percentage_by_vocabulary
        },
        headers={'Cache-Control': 'no-store'}
    )


@app.get("/new_session")
async def new_session(request: Request,
                      voc_id: int,
                      user: User = Depends(get_user)):

    voc = db.get_vocabulary(user, voc_id)

    session = db.create_new_session(user, voc)

    return RedirectResponse(url=f'/learn?session_id={session.id}')


@app.get("/learn")
async def learn(request: Request,
                response: Response,
                session_id: int):
    session = db.load_session(session_id)

    first_word = None
    first_word_id = None
    if session.current_word is not None:
        current_word = session.current_word
        vocabulary = session.vocabulary
        first_word = WordInput(word=current_word.word_input,
                               word_id=vocabulary.word_id(current_word))

    ret = TEMPLATES.TemplateResponse(
        "learn.html",
        {
            'request': request,
            'session': session,
            'first_word': first_word,
        },
        headers={'Cache-Control': 'no-store'}
    )

    return ret


@app.post("/word")
async def post_word(word_output: WordOutput):
    session = db.load_session(word_output.session_id)
    vocabulary = session.vocabulary

    current_word = vocabulary.word(word_output.word_id)
    hint_word = current_word.word_output

    result = session.guess(current_word, word_output.word)

    success = False
    if result is not None:
        db.add_word(session, result)
        success = result.success

    next_word_input = None
    if session.current_word is not None:
        next_word = session.current_word
        vocabulary = session.vocabulary
        next_word_input = WordInput(word=next_word.word_input,
                                    word_id=vocabulary.word_id(next_word))

    return WordResult(success=success,
                      hint=hint_word,
                      word_input=WordInput(word=current_word.word_input,
                                           word_id=word_output.word_id),
                      word_output=word_output,
                      next_word=next_word_input)

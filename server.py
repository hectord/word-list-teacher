
from typing import Optional
from pathlib import Path
import secrets

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from starlette.responses import RedirectResponse
from pydantic import BaseModel

from learn import Vocabulary, LearnEngine, Word
from store import load_database, DbUser, DbException


BASE_PATH = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_PATH / "templates"))

VOCABULARIES = BASE_PATH / 'learn.db'

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
security = HTTPBasic()


class WordInput(BaseModel):
    word: str


class WordOutput(BaseModel):
    word: str
    session_id: int


class WordResult(BaseModel):
    success: bool

    word_input: WordInput
    word_output: WordOutput

    hint: Optional[str]

    # if None => no more word
    next_word: Optional[WordInput]


def get_user(creds: HTTPBasicCredentials = Depends(security)):
    db = load_database(VOCABULARIES)
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


@app.get("/index")
def index(request: Request, user: DbUser = Depends(get_user)):
    db = load_database(VOCABULARIES)
    vocabularies = db.list_vocabularies()
    session_by_vocabulary = {}

    for vocabulary in vocabularies.values():
        session = db.last_session(user, vocabulary)
        if session is not None:
            session_by_vocabulary[vocabulary] = session

    return TEMPLATES.TemplateResponse(
        "index.html",
        {
            'request': request,
            'vocabularies': vocabularies,
            'session_by_vocabulary': session_by_vocabulary
        }
    )


@app.get("/new_session")
def new_session(request: Request,
                voc_id: int,
                user: DbUser = Depends(get_user)):
    db = load_database(VOCABULARIES)

    voc = db.get_vocabulary(voc_id)

    session_id = db.create_new_session(user, voc)

    return RedirectResponse(url=f'/learn?session_id={session_id}')


@app.get("/learn")
def learn(request: Request, session_id: int):
    db = load_database(VOCABULARIES)
    engine = db.load_session(session_id)

    current_word = engine.current_word
    first_word = WordInput(word=current_word.word_input)

    return TEMPLATES.TemplateResponse(
        "learn.html",
        {
            'request': request,
            'session_id': session_id,
            'first_word': first_word
        }
    )


@app.post("/word")
def post_word(word: WordOutput):
    db = load_database(VOCABULARIES)
    engine = db.load_session(word.session_id)

    current_word = engine.current_word
    hint_word = current_word.word_output

    result = engine.guess(word.word)

    db = load_database(VOCABULARIES)
    db.add_word(engine, result)

    next_word = None
    if engine.current_word is not None:
        next_word = WordInput(word=engine.current_word.word_input)

    return WordResult(success=result.success,
                      hint=hint_word,
                      word_input=WordInput(word=current_word.word_input),
                      word_output=word,
                      next_word=next_word)

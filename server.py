
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
from store import load_database


BASE_PATH = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_PATH / "templates"))

VOCABULARIES = BASE_PATH / 'learn.db'

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
security = HTTPBasic()

engine = None


class WordInput(BaseModel):
    word: str


class WordOutput(BaseModel):
    word: str


class WordResult(BaseModel):
    success: bool

    word_input: WordInput
    word_output: WordOutput

    hint: Optional[str]

    # if None => no more word
    next_word: Optional[WordInput]


def get_current_username(creds: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(creds.username, "stanleyjobson")
    correct_password = secrets.compare_digest(creds.password, "swordfish")
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return creds.username


@app.get("/")
def root():
    return RedirectResponse(url='/index')


@app.get("/index")
def index(request: Request, username: str = Depends(get_current_username)):
    db = load_database(VOCABULARIES)
    vocabularies = db.list_vocabularies()

    return TEMPLATES.TemplateResponse(
        "index.html",
        {
            'request': request,
            'vocabularies': vocabularies
        }
    )


@app.get("/learn")
def learn(request: Request):
    global engine
    new_voc = Vocabulary.load("vocabulary/test.txt")
    engine = LearnEngine(new_voc)

    current_word = engine.current_word
    first_word = WordInput(word=current_word.word_input)

    return TEMPLATES.TemplateResponse(
        "learn.html",
        {
            'request': request,
            'first_word': first_word
        }
    )


@app.post("/word")
def post_word(word: WordOutput):
    current_word = engine.current_word
    hint_word = current_word.word_output

    success = engine.guess(word.word)

    next_word = None
    if engine.current_word is not None:
        next_word = WordInput(word=engine.current_word.word_input)

    return WordResult(success=success,
                      hint=hint_word,
                      word_input=WordInput(word=current_word.word_input),
                      word_output=word,
                      next_word=next_word)

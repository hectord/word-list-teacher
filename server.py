
from typing import Optional
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import RedirectResponse

from learn import Vocabulary, LearnEngine, Word

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")


def json_word(word: Word):
    return {
        "input": word.word,
        "result": word.word_french
    }


@app.get("/")
def root():
    return RedirectResponse(url='/static/learn.html')

@app.post("/new_session")
def new_session():
    new_voc = Vocabulary.load("vocabulary/test.txt")

    engine = LearnEngine(new_voc)
    current_word = engine.current_word

    return {
        "word": json_word(current_word)
    }

@app.get("/items/{item_id}")
def read_item(item_id: int, q: Optional[str] = None):
    return {"item_id": item_id, "q": q}

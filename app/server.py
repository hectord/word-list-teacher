# -*- coding: utf-8 -*-

import math
import os
from typing import Optional, List
from datetime import date, timedelta
from pathlib import Path

from fastapi import (FastAPI, Form, Request, Response, Depends,
                     HTTPException, status)
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from starlette.responses import RedirectResponse
from pydantic import BaseModel

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

    # when the correct answer was a different accepted variant than the
    # one this exercise expected, show both so the expected variant is
    # learnt even though another was used
    used_other_variant: bool = False

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
                        hard_runs: Optional[int] = Form(None),
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

    if hard_runs is not None:
        if not 1 <= hard_runs <= 50:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="hard_runs must be between 1 and 50")
        db.set_user_hard_runs(user, hard_runs)

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
    # a word is hard when it was answered wrongly at least once during
    # the last N runs which included it (N = the user's setting)
    unknown_count = sum(1 for word in voc.words if stats.hard_for(word))

    def section_progress(words):
        """(included, mastered) counts for a list of words, using the
        same hard-word rule as the vocabulary page."""
        included = mastered = 0
        for word in words:
            if stats.included_for(word):
                included += 1
                if not stats.hard_for(word):
                    mastered += 1
        size = len(words)
        seen = included - mastered
        return {
            'included': included,
            'mastered': mastered,
            'seen': seen,
            'never': size - included,
            'pct_mastered': 100 * mastered // size if size else 0,
            'pct_seen': 100 * seen // size if size else 0,
        }

    whole_progress = section_progress(voc.words)

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
            'progress': section_progress(section.vocabulary.words),
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
            'whole_progress': whole_progress,
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
    included_by_vocabulary = {}
    mastered_by_vocabulary = {}
    seen_by_vocabulary = {}
    never_by_vocabulary = {}
    mastered_percentage_by_vocabulary = {}
    seen_percentage_by_vocabulary = {}
    progress = db.progress_word_counts(user, levels)
    total_words = 0
    total_included = 0
    total_mastered = 0
    entries = []

    for voc_id, vocabulary in vocabularies.items():
        session = db.last_session(user, vocabulary)
        if session is not None and not session.is_finished:
            session_by_vocabulary[vocabulary] = session

        finished_session = db.last_session(user, vocabulary, finished=True)
        has_finished_session[vocabulary] = finished_session is not None

        size = len(vocabulary)
        included, mastered = progress.get(voc_id, (0, 0))
        seen = included - mastered
        never = size - included

        included_by_vocabulary[vocabulary] = included
        mastered_by_vocabulary[vocabulary] = mastered
        seen_by_vocabulary[vocabulary] = seen
        never_by_vocabulary[vocabulary] = never
        mastered_percentage_by_vocabulary[vocabulary] = \
            (100 * mastered // size) if size else 0
        seen_percentage_by_vocabulary[vocabulary] = \
            (100 * seen // size) if size else 0
        total_words += size
        total_included += included
        total_mastered += mastered
        entries.append((voc_id, vocabulary))

    # practised vocabularies first, the weakest (least mastered) on top;
    # vocabularies never practised come last
    def sort_key(entry):
        vocabulary = entry[1]
        practised = (has_finished_session.get(vocabulary, False) or
                     vocabulary in session_by_vocabulary)
        return (
            0 if practised else 1,
            mastered_percentage_by_vocabulary.get(vocabulary, 0),
            entry[0],
        )

    entries.sort(key=sort_key)

    total_seen = total_included - total_mastered
    total_never = total_words - total_included
    mastered_percentage = \
        (100 * total_mastered // total_words) if total_words else 0
    seen_percentage = (100 * total_seen // total_words) if total_words else 0
    # exact: never = whatever the first two segments do not cover
    never_percentage = 100 - mastered_percentage - seen_percentage

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
            'included_by_vocabulary': included_by_vocabulary,
            'mastered_by_vocabulary': mastered_by_vocabulary,
            'seen_by_vocabulary': seen_by_vocabulary,
            'never_by_vocabulary': never_by_vocabulary,
            'mastered_percentage_by_vocabulary': mastered_percentage_by_vocabulary,
            'seen_percentage_by_vocabulary': seen_percentage_by_vocabulary,
            'total_words': total_words,
            'total_included': total_included,
            'total_mastered': total_mastered,
            'total_seen': total_seen,
            'total_never': total_never,
            'mastered_percentage': mastered_percentage,
            'seen_percentage': seen_percentage,
            'never_percentage': never_percentage,
        },
        headers={'Cache-Control': 'no-store'}
    )


@app.get("/scoreboard")
async def scoreboard(request: Request,
                     user: User = Depends(get_user)):

    # the board is scored within the levels the viewing user has to
    # learn: words above that level are skipped everywhere
    levels = included_levels(user.level)
    sizes = db.all_vocabulary_sizes(levels)
    total_words = sum(sizes.values())

    mastered_by_user = db.mastered_counts_by_user(levels)

    entries = []
    for user_id, email in db.list_users():
        per_vocabulary = mastered_by_user.get(user_id, {})
        mastered = sum(per_vocabulary.get(voc_id, 0) for voc_id in sizes)
        percentage = (100 * mastered // total_words) if total_words else 0
        entries.append({
            'email': email,
            'mastered': mastered,
            'total': total_words,
            'percentage': percentage,
            'is_me': email == user.email,
        })

    entries.sort(key=lambda e: (e['percentage'], e['mastered']),
                 reverse=True)

    # bars are relative to the best user so they are readable at any scale
    best = entries[0]['mastered'] if entries else 0
    for entry in entries:
        entry['bar_percentage'] = \
            (100 * entry['mastered'] // best) if best else 0

    return TEMPLATES.TemplateResponse(
        request, "scoreboard.html",
        {
            'user': user,
            'entries': entries,
            'total_words': total_words,
        },
        headers={'Cache-Control': 'no-store'}
    )


def _format_duration(seconds) -> str:
    """A compact human duration ("45s", "12m", "1h 05m")."""
    seconds = int(round(seconds))
    if seconds < 60:
        return '%ds' % seconds
    minutes = seconds // 60
    if minutes < 60:
        return '%dm' % minutes
    return '%dh %02dm' % (minutes // 60, minutes % 60)


def _hourly_chart(hours) -> dict:
    """Bar chart of the attempts per hour of the day: successful ones
    and errors side by side."""
    if not any(h['successes'] or h['failures'] for h in hours):
        return {'has_data': False}

    W, H = 940, 260
    PL, PR, PT, PB = 46, 18, 18, 30
    plot_w, plot_h = W - PL - PR, H - PT - PB

    top = max(max(h['successes'], h['failures']) for h in hours) or 1
    group = plot_w / len(hours)
    bar_w = max(4.0, group * 0.32)

    def ypx(value):
        return PT + plot_h * (1 - value / top)

    bars = []
    for index, hour in enumerate(hours):
        centre = PL + group * (index + 0.5)
        for offset, key, css in ((-bar_w / 2, 'successes', 'success'),
                                 (bar_w / 2, 'failures', 'error')):
            value = hour[key]
            if not value:
                continue
            y = ypx(value)
            bars.append({
                'x': '%.1f' % (centre + offset - bar_w / 2),
                'y': '%.1f' % y,
                'width': '%.1f' % bar_w,
                'height': '%.1f' % (PT + plot_h - y),
                'css': css,
                'title': 'hour %02d-%02d: %d %s' % (
                    hour['hour'], hour['hour'] + 1, value,
                    'correct' if key == 'successes' else 'wrong'),
            })

    gridlines = []
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        value = fraction * top
        gridlines.append({'y': '%.1f' % ypx(value),
                          'label': '%d' % round(value)})

    x_labels = []
    for hour in range(0, 24, 3):
        centre = PL + group * (hour + 0.5)
        x_labels.append({'x': '%.1f' % centre,
                         'text': '%dh' % hour})

    return {
        'has_data': True,
        'width': W,
        'height': H,
        'pl': PL,
        'pr': W - PR,
        'pb': H - PB,
        'bars': bars,
        'gridlines': gridlines,
        'x_labels': x_labels,
        'successes': sum(h['successes'] for h in hours),
        'failures': sum(h['failures'] for h in hours),
        'peak': top,
    }


WEEKDAYS = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')


def _weekday_chart(days) -> dict:
    """Bar chart of the attempts per day of the week: successful ones
    and errors side by side."""
    if not any(d['successes'] or d['failures'] for d in days):
        return {'has_data': False}

    W, H = 940, 260
    PL, PR, PT, PB = 46, 18, 18, 30
    plot_w, plot_h = W - PL - PR, H - PT - PB

    top = max(max(d['successes'], d['failures']) for d in days) or 1
    group = plot_w / len(days)
    bar_w = min(44.0, max(6.0, group * 0.24))

    def ypx(value):
        return PT + plot_h * (1 - value / top)

    bars = []
    for index, day in enumerate(days):
        centre = PL + group * (index + 0.5)
        for offset, key, css in ((-bar_w / 2, 'successes', 'success'),
                                 (bar_w / 2, 'failures', 'error')):
            value = day[key]
            if not value:
                continue
            y = ypx(value)
            bars.append({
                'x': '%.1f' % (centre + offset - bar_w / 2),
                'y': '%.1f' % y,
                'width': '%.1f' % bar_w,
                'height': '%.1f' % (PT + plot_h - y),
                'css': css,
                'title': '%s: %d %s' % (
                    WEEKDAYS[day['weekday']], value,
                    'correct' if key == 'successes' else 'wrong'),
            })

    gridlines = []
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        value = fraction * top
        gridlines.append({'y': '%.1f' % ypx(value),
                          'label': '%d' % round(value)})

    x_labels = []
    for index in range(len(days)):
        centre = PL + group * (index + 0.5)
        x_labels.append({'x': '%.1f' % centre, 'text': WEEKDAYS[index]})

    return {
        'has_data': True,
        'width': W,
        'height': H,
        'pl': PL,
        'pr': W - PR,
        'pb': H - PB,
        'bars': bars,
        'gridlines': gridlines,
        'x_labels': x_labels,
        'successes': sum(d['successes'] for d in days),
        'failures': sum(d['failures'] for d in days),
        'peak': top,
    }


def _markov_chart(transitions) -> dict:
    """The Markov-chain diagram: states are the number of correct
    attempts a word has; each attempt advances the state with the
    probability of answering correctly or keeps it (self loop)."""
    states = [s for s in transitions]
    if not any(s['attempts'] for s in states):
        return {'has_data': False}

    W, H = 940, 300
    margin = 66
    cy = 172
    radius = 22
    count = len(states)
    spacing = (W - 2 * margin) / count if count else W

    nodes = []
    for index, state in enumerate(states):
        x = margin + spacing * (index + 0.5)
        attempts = state['attempts']
        nodes.append({
            'state': state['state'],
            'x': '%.1f' % x,
            'cy': cy,
            'attempts': attempts,
            'reached': attempts > 0,
            'success_rate': (100.0 * state['successes'] / attempts)
                            if attempts else 0.0,
            'stay_rate': (100.0 * state['failures'] / attempts)
                         if attempts else 0.0,
        })

    edges = []
    loops = []
    for index, node in enumerate(nodes[:-1]):
        if not node['reached']:
            continue
        following = nodes[index + 1]
        rate = node['success_rate']
        edges.append({
            'x1': '%.1f' % (float(node['x']) + radius),
            'x2': '%.1f' % (float(following['x']) - radius - 6),
            'y': cy,
            'label_x': '%.1f' % ((float(node['x']) +
                                  float(following['x'])) / 2),
            'label_y': cy - 12,
            'probability': '%.0f%%' % rate,
            'title': '%d transition(s), %d correct' % (
                node['attempts'],
                round(node['attempts'] * rate / 100.0)),
            'visible': rate > 0,
        })

    for node in nodes:
        if not node['reached'] or node['stay_rate'] <= 0:
            continue
        x = float(node['x'])
        loops.append({
            'x1': '%.1f' % (x - radius * 0.45),
            'x2': '%.1f' % (x + radius * 0.45),
            'y': cy - radius,
            'label_x': '%.1f' % x,
            'label_y': cy - radius - 52,
            'probability': '%.0f%%' % node['stay_rate'],
            'title': '%d transition(s), %d wrong' % (
                node['attempts'],
                round(node['attempts'] * node['stay_rate'] / 100.0)),
        })

    return {
        'has_data': True,
        'width': W,
        'height': H,
        'nodes': nodes,
        'edges': [e for e in edges if e['visible']],
        'loops': loops,
    }


def _pick_title(summary: dict) -> str:
    titles = summary.get('titles', {})
    for code in ('en', 'de', 'fr', 'es', 'it', 'nl', 'pt'):
        if code in titles:
            return titles[code]
    if titles:
        return next(iter(titles.values()))
    return f"vocabulary {summary['id']}"


def _over_time_chart(daily) -> dict:
    """Turn ``{date: (mastered, learned)}`` into an SVG line chart."""
    W, H = 940, 300
    PL, PR, PT, PB = 46, 18, 18, 30
    ordered = sorted(daily)
    first, last = ordered[0], ordered[-1]
    days = (last - first).days + 1

    # fill empty days by carrying the last value forward
    series = []
    carried_k = carried_l = 0
    d = first
    for _ in range(days):
        if d in daily:
            carried_k, carried_l = daily[d]
        series.append((carried_k, carried_l))
        d += timedelta(days=1)

    ymax = max((max(k, l) for k, l in series), default=1) or 1
    plot_w, plot_h = W - PL - PR, H - PT - PB

    def xpx(i):
        return PL + plot_w * i / (days - 1) if days > 1 else PL + plot_w / 2

    def ypx(v):
        return PT + plot_h * (1 - v / ymax)

    points_mastered = ' '.join(
        f'{xpx(i):.1f},{ypx(k):.1f}' for i, (k, _) in enumerate(series))
    points_learned = ' '.join(
        f'{xpx(i):.1f},{ypx(l):.1f}' for i, (_, l) in enumerate(series))

    gridlines = []
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        value = fraction * ymax
        gridlines.append({'y': f'{ypx(value):.1f}',
                          'label': f'{round(value)}'})

    x_labels = []
    for i in {0, days // 2, days - 1}:
        x_labels.append({'x': f'{xpx(i):.1f}',
                         'text': str(first + timedelta(days=i))})

    last_x = f'{xpx(days - 1):.1f}'
    return {
        'has_data': True,
        'points_mastered': points_mastered,
        'points_learned': points_learned,
        'gridlines': gridlines,
        'x_labels': x_labels,
        'last_x': last_x,
        'last_mastered_y': f'{ypx(series[-1][0]):.1f}',
        'last_learned_y': f'{ypx(series[-1][1]):.1f}',
        'last_mastered': series[-1][0],
        'last_learned': series[-1][1],
        'ymax': ymax,
        'days': days,
        'first_day': str(first),
    }


@app.get("/stats")
async def stats(request: Request,
                voc: Optional[str] = None,
                user: User = Depends(get_user)):

    # stats are always about the signed-in user, within the levels they
    # have to learn: words above that level are skipped everywhere
    levels = included_levels(user.level)
    sizes = db.all_vocabulary_sizes(levels)
    summaries = db.vocabulary_summaries()

    voc_options = [{'id': s['id'], 'title': _pick_title(s),
                    'size': sizes.get(s['id'], 0)}
                   for s in summaries if sizes.get(s['id'], 0) > 0]

    # the filter form submits an empty value for "All vocabularies";
    # parse it leniently instead of letting FastAPI 422 on ""
    selected_voc = None
    if voc:
        try:
            requested = int(voc)
        except ValueError:
            requested = None
        if requested is not None and \
                any(o['id'] == requested for o in voc_options):
            selected_voc = requested

    total_words = sum(o['size'] for o in voc_options
                      if selected_voc is None or o['id'] == selected_voc)
    daily = db.mastered_over_time(user, voc_id=selected_voc, levels=levels)

    # how words move between the states "correct attempts so far"
    markov = _markov_chart(
        db.attempt_state_transitions(user, voc_id=selected_voc,
                                     levels=levels))

    # attempts per hour of the day (correct vs wrong)
    hourly = _hourly_chart(
        db.attempts_by_hour(user, voc_id=selected_voc, levels=levels))

    # attempts per day of the week (correct vs wrong)
    weekday = _weekday_chart(
        db.attempts_by_weekday(user, voc_id=selected_voc, levels=levels))

    # practice consistency: days practised vs. days since the start,
    # and the average active time on a practised day
    practice = db.practice_stats(user, voc_id=selected_voc, levels=levels)
    practice['average'] = _format_duration(practice['average_seconds'])
    practice['active'] = _format_duration(practice['active_seconds'])

    mastered_now = learned_now = days_practised = 0
    chart = {'has_data': False}
    eta = None
    if daily:
        mastered_now, learned_now = daily[sorted(daily)[-1]]
        days_practised = len(daily)
        chart = _over_time_chart(daily)

        # completion estimate: the overall pace (mastered words per day
        # since the first practice day, up to today) extrapolated to the
        # remaining words of the current scope
        first_day = sorted(daily)[0]
        elapsed = (date.today() - first_day).days + 1
        pace = mastered_now / elapsed if elapsed else 0.0
        remaining = total_words - mastered_now
        if remaining <= 0:
            eta = {'done': True}
        elif pace > 0:
            days = math.ceil(remaining / pace)
            eta = {
                'pace': pace,
                'remaining': remaining,
                'days': days,
                'date': (date.today() + timedelta(days=days)).isoformat(),
            }

    return TEMPLATES.TemplateResponse(
        request, "stats.html",
        {
            'user': user,
            'voc_options': voc_options,
            'selected_voc': selected_voc,
            'total_words': total_words,
            'mastered_now': mastered_now,
            'learned_now': learned_now,
            'days_practised': days_practised,
            'chart': chart,
            'markov': markov,
            'hourly': hourly,
            'weekday': weekday,
            'practice': practice,
            'eta': eta,
        },
        headers={'Cache-Control': 'no-store'}
    )


@app.get("/hard-words")
async def hard_words(request: Request,
                     user: User = Depends(get_user)):

    target = _resolve_target(user)
    levels = included_levels(user.level)

    if target is None:
        return TEMPLATES.TemplateResponse(
            request, "hard_words.html",
            {'user': user, 'groups': [], 'total': 0, 'target': None},
            headers={'Cache-Control': 'no-store'}
        )

    vocabularies = db.list_vocabularies(user, target, levels=levels)
    hard = db.hard_word_ids(user, levels=levels)

    groups = []
    total = 0
    for voc in vocabularies.values():
        entries = []
        for word in voc.words:
            word_id = voc.word_id(word)
            if word_id is not None and word_id in hard:
                entries.append({
                    'word': word.word_output,
                    'input': word.word_input,
                    'misses': hard[word_id],
                })
        if not entries:
            continue

        entries.sort(key=lambda entry: (-entry['misses'], entry['word']))
        total += len(entries)
        groups.append({
            'id': voc.id,
            'title': voc.name.word_input if voc.name else 'Vocabulary',
            'entries': entries,
        })

    # the most problematic vocabularies first
    groups.sort(key=lambda group: (-len(group['entries']), group['title']))

    return TEMPLATES.TemplateResponse(
        request, "hard_words.html",
        {
            'user': user,
            'groups': groups,
            'total': total,
            'target': target,
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
    """End-of-run summary: words known (no mistake) out of the total,
    the words to learn again, and - for the AI strategy - how many
    words are new, newly mastered or newly hard compared to before the
    run."""
    if not session.is_finished:
        return None

    ai_delta = None
    if session.strategy_name == 'ai':
        word_ids = [word.id for word in session.run.words]
        before = db.word_states(user, session.vocabulary.id, word_ids,
                                exclude_session=session.id)
        after = db.word_states(user, session.vocabulary.id, word_ids)

        def count(key):
            return sum(1 for word_id, state in after.items()
                       if state[key] and not before.get(word_id, (0, 0, 0))[key])

        ai_delta = {
            'new_words': count(0),
            'new_mastered': count(1),
            'new_hard': count(2),
        }

    return session.summary(ai_delta)


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

    # for already-answered cards: which ones used another correct variant
    # than the expected one (shown on resume, like during the run)
    output_language = session.vocabulary.output_language
    variant_notes = [
        attempt.success and attempt.word.is_other_variant(
            attempt.typed_word, output_language)
        for attempt in session.attempts
    ]

    ret = TEMPLATES.TemplateResponse(
        request, "learn.html",
        {
            'session': session,
            'first_word': first_word,
            'summary': _session_summary(session, user),
            'variant_notes': variant_notes,
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
    used_other_variant = False
    if result is not None:
        db.add_word_attempt(session, result)
        success = result.success
        used_other_variant = current_word.is_other_variant(
            word_output.word, vocabulary.output_language)

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
                      used_other_variant=used_other_variant,
                      next_word=next_word_input,
                      summary=_session_summary(session, user))

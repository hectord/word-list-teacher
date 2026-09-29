[![CI](https://github.com/hectord/word-list-teacher/actions/workflows/ci.yml/badge.svg)](https://github.com/hectord/word-list-teacher/actions)

# Word list teacher (WLT)

Teach someone a new language through vocabulary.

How does WLT plan to do it?

* provide a way to learn a vocabulary
* extract which words have to be learned every day

Long term goal

* make it a platform (smartphone + web)
* make statistics available to everybody (anonymized)
* speed up the learning process for any language

## Getting started (local)

```bash
# 1. setup the environment (once)
python3 -m venv myenv
myenv/bin/pip install -r requirements.txt

# 2. start the server (see run.sh for HOST/PORT/RELOAD overrides)
./run.sh
```

The server runs on http://127.0.0.1:8000 and uses the database at
`data/learn.db` (created on first start, ignored by git).

## Dictionary & CLI

Vocabularies are loaded into the database with the CLI (`app/cli.py`).
A vocabulary is language agnostic: it has a title, sections and words, and
each of them has one text per language (plus an optional example sentence).

```bash
# initialize the languages (once per fresh database)
myenv/bin/python app/cli.py database data/learn.db init

# create a user with their main language (the language they know) and
# their level (A2, B1, B2 or C1). On the index page they then pick the
# language to practise and the level (both saved in their profile for
# the level)
myenv/bin/python app/cli.py database data/learn.db \
    create-user you@example.com --main-language fr --level B1

# import a cleaned dictionary (assumed German -> French):
# vocabulary;section;german;translation
myenv/bin/python app/cli.py database data/learn.db \
    add-dictionary data/merged.cleaned
```

Useful commands: `list-vocabularies`, `list-sections <voc-id>`,
`list-words <voc-id>`, `add-vocabulary <file>`, `remove-vocabulary <voc-id>`,
`set-user-level <email> <level>`,
`add-word <voc-id> --input-language fr --output-language de <in> <out>`,
`update-word <word-id> --language de [--text <text>] [--example <sentence>] [--type noun] [--level B1]`.

## Docker image

```bash
docker build -t wlt .
docker run -d --name wlt -v $PWD/data:/data -p 8000:80 wlt
```

The database lives on the mounted `./data` volume (`/data/learn.db` inside
the container). The first time you run it, initialize the database and import
your vocabulary from the host using the repository venv (see above — the
commands are the same, against `data/learn.db`, which is the mounted volume).

## CI / Deployment

**CI** — unit tests run on every **pull request** via GitHub Actions
(`.github/workflows/ci.yml`: Python 3.13, `pip install -r requirements.txt`,
`python -m unittest`).

**Deploy** — pushing to `main` (or a manual `workflow_dispatch` run) triggers
`.github/workflows/deploy.yml`, which first runs the same unit tests and,
only if they pass, proceeds with the deployment:

1. builds the Docker image and publishes it to the GitHub Container
   Registry (`ghcr.io/<repo>:latest` and `:<commit sha>`),
2. connects over SSH to the production server, pulls the image, and restarts
   the `wlt` container with `--restart unless-stopped`, mapping host port
   `8000` to the container's port `80`, with the data volume mounted.

To enable the automatic deployment, add these **repository secrets**
(Settings → Secrets and variables → Actions):

| Secret            | Description                                                     | Default            |
|-------------------|-----------------------------------------------------------------|--------------------|
| `DEPLOY_HOST`     | address of the production server                                | (required)         |
| `DEPLOY_SSH_KEY`  | private ssh key with access to the server                       | (required)         |
| `DEPLOY_USER`     | ssh user                                                        | `root`             |
| `DEPLOY_PORT`     | ssh port                                                        | `22`               |
| `DEPLOY_PATH`     | server directory for the `data` volume                          | derived, see below |

If `DEPLOY_PATH` is not set, the data volume path is derived from the ssh
user: `/root/wlt/data` when `DEPLOY_USER` is `root`, otherwise
`/home/<user>/wlt/data`. The database is stored at `<path>/data/learn.db`.

If `DEPLOY_HOST` or `DEPLOY_SSH_KEY` are missing, the workflow still builds
and publishes the image, and prints a "skip deploy" notice instead of failing.

On the server, initialize the database once (the container starts with an
empty volume):

```bash
docker exec -it wlt python cli.py database /data/learn.db init
docker exec -it wlt python cli.py database /data/learn.db \
    create-user you@example.com --speaks fr
# then import your dictionary file, mounted or copied into the container
```

## FAQ

### How can I start the server?

> ./run.sh

or directly with uvicorn (from the `app/` directory):

> uvicorn server:app --reload
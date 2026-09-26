[![CI](https://github.com/hectord/word-list-teacher/actions/workflows/ci.yml/badge.svg)](https://github.com/hectord/word-list-teacher/actions)

## CI / Deployment

Unit tests run on every push via GitHub Actions (`.github/workflows/ci.yml`).

Pushing to `main` also builds the Docker image, publishes it to the GitHub
Container Registry, and deploys it to the production server
(`.github/workflows/deploy.yml`). To enable the automatic deployment, add
these repository secrets:

* `DEPLOY_HOST` — address of the production server
* `DEPLOY_USER` — ssh user (defaults to `root` when missing)
* `DEPLOY_PORT` — ssh port (defaults to `22`)
* `DEPLOY_SSH_KEY` — private ssh key with access to the server
* `DEPLOY_PATH` — directory on the server where the `data` volume lives
  (defaults to `~/wlt`; the database is stored at `./data/learn.db`)

On the server the image runs as container `wlt`, mapping host port `8000`
to the container's port 80, with `--restart unless-stopped`.

# Word list teacher (WLT)

Teach someone a new language through vocabulary.

How does WLT plan to do it?

* provide a way to learn a vocabulary
* extract which words have to be learned every day

Long term goal

* make it a platform (smartphone + web)
* make statistics available to everybody (anonymized)
* speed up the learning process for any language

## FAQ

### How can I start the server?

> uvicorn server:app --reload

### How do I create a Docker container?

> docker build . -t myimage

> docker run -d --name wlt -v $PWD/data:/data -p 8000:80 myimage

The database lives on the mounted `./data` volume (`/data/learn.db` inside the
container). The first time you run it, initialize the database and import your
vocabulary from the host using the repository venv:

> myenv/bin/python app/cli.py database data/learn.db init
> myenv/bin/python app/cli.py database data/learn.db create-user you@example.com --speaks fr
> myenv/bin/python app/cli.py database data/learn.db add-dictionary data/merged.cleaned

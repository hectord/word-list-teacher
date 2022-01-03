[![CircleCI](https://circleci.com/gh/hectord/word-list-teacher/tree/master.svg?style=svg)](https://circleci.com/gh/hectord/word-list-teacher/tree/master)

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
> docker run -it -v $PWD/data:/data -p 8000:80 myimage

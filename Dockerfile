FROM python:3.13-slim

ENV DATADIR=/data

WORKDIR /code

COPY requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir -r /code/requirements.txt

COPY app /code

EXPOSE 80

# The database lives on a mounted volume (e.g. -v $PWD/data:/data),
# see the README. Inside the container /data/learn.db is used.
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "80"]
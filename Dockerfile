FROM registry.gitlab.com/thelabnyc/python:py313
ENV PYTHONUNBUFFERED 1

RUN mkdir /code
WORKDIR /code

ADD . /code/
RUN poetry install

FROM registry.gitlab.com/thelabnyc/python:3.14@sha256:71a092cc050bcfb3e795237c18521e964240331355ef059637a6a37b6bfffc3e
ENV PYTHONUNBUFFERED 1

RUN mkdir /code
WORKDIR /code

ADD . /code/
RUN uv sync

FROM registry.gitlab.com/thelabnyc/python:3.14@sha256:58ee440298b582ac3dab1cfeed3671b7c8a6b2f798a496c8ba423795328f26fb
ENV PYTHONUNBUFFERED 1

RUN mkdir /code
WORKDIR /code

ADD . /code/
RUN uv sync

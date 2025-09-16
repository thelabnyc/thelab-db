FROM registry.gitlab.com/thelabnyc/python:3.13.957@sha256:db0566fc8c17a188cd079238813ae6df4010c7fa586f4fefcfa8c4bd34c0acfb
ENV PYTHONUNBUFFERED 1

RUN mkdir /code
WORKDIR /code

ADD . /code/
RUN uv sync

FROM python:3.9-bookworm AS base

WORKDIR /project

VOLUME ["/media"]
VOLUME ["/static"]

COPY poetry.lock pyproject.toml /project/
ENV POETRY_VIRTUALENVS_CREATE=false

# hadolint ignore=DL3008
RUN apt-get update && apt-get install --no-install-recommends -y \
  default-mysql-client \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# Use pip to install poetry. We don't use virtualenvs in the build context.
# Therefore, the vendored install provides no additional isolation.
RUN \
  pip install --no-cache-dir "poetry~=1.1" && \
  poetry install --no-dev --no-root && \
  mkdir /var/log/django

EXPOSE 80 443

FROM base AS dev

# dev only
RUN poetry install

FROM base AS release

COPY . /project


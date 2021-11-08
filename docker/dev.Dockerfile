ARG PY_IMG_TAG=3.9.7

FROM python:${PY_IMG_TAG} as base

WORKDIR /project

VOLUME ["/media"]
VOLUME ["/static"]

COPY poetry.lock pyproject.toml /project/
ENV POETRY_VIRTUALENVS_CREATE=false

# Use pip to install poetry. We don't use virtualenvs in the build context.
# Therefore, the vendored install provides no additional isolation.
RUN \
  pip install --no-cache-dir "poetry~=1.1" && \
  poetry install --no-root && \
  mkdir /var/log/django

EXPOSE 80 443

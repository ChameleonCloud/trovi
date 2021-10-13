ARG PY_IMG_TAG=3.9.7

FROM python:${PY_IMG_TAG}

COPY . /project
WORKDIR /project

VOLUME ["/media"]
VOLUME ["/static"]

COPY poetry.lock pyproject.toml /setup/
ENV POETRY_VIRTUALENVS_CREATE=false

# Use pip to install poetry. We don't use virtualenvs in the build context.
# Therefore, the vendored install provides no additional isolation.
RUN \
  pip install --upgrade pip && \
  pip install "poetry~=1.1" && \
  poetry install --no-dev --no-root && \
  mkdir /var/log/django

EXPOSE 80 443

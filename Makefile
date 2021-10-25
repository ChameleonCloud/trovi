# Set make variables from .env file
ifneq (,$(wildcard ./.env))
	include .env
	export
	ENV_FILE_PARAM = --env-file .env
endif

DOCKER_TAG ?= $(shell git rev-parse --short HEAD)
DOCKER_IMAGE ?= $(DOCKER_REGISTRY)/trovi:$(DOCKER_TAG)
DOCKER_IMAGE_LATEST ?= $(DOCKER_REGISTRY)/trovi:latest
PY_IMG_TAG ?= 3.9.7

.env:
	cp .env.sample .env

.PHONY: build
build: .env
	docker build --build-arg PY_IMG_TAG=$(PY_IMG_TAG) \
				 -t $(DOCKER_IMAGE) .
	docker tag $(DOCKER_IMAGE) $(DOCKER_IMAGE_LATEST)

.PHONY: publish
publish:
	docker push $(DOCKER_IMAGE)

.PHONY: publish-latest
publish-latest:
	docker push $(DOCKER_IMAGE_LATEST)

.PHONY: start
start: .env
	docker-compose $(ENV_FILE_PARAM) up -d

.PHONY: clean
clean:
	docker-compose $(ENV_FILE_PARAM) down

.PHONY: migrations
migrations: start
	docker-compose exec trovi python manage.py makemigrations --check

requirements-frozen.txt: build
	docker run --rm $(DOCKER_IMAGE) pip freeze > $@

COMPOSE_TEST_CMD :=  docker-compose -f tests-compose.yml

.PHONY: deploy-tests
deploy-tests:
	$(COMPOSE_TEST_CMD) run --rm trovi migrate
	$(COMPOSE_TEST_CMD) run --rm trovi collectstatic --no-input

.PHONY: deploy-tests-clean
deploy-tests-clean:
	$(COMPOSE_TEST_CMD) down -v

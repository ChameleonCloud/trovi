# Trovi

Trovi is a platform for sharing and reproducing research artifacts. It provides a REST API for use by various clients.

## Documentation
Read our documentation on [GitBook!](https://chameleoncloud.gitbook.io/trovi/)

## Development

Trovi is a Django application built on [Django REST Framework](https://www.django-rest-framework.org)
which is designed to run in a Docker container. Trovi is written in Python 3.9. Developing for Trovi requires little
setup.

### Building the development image

```shell
$ make build-dev
```

You can also build and run Trovi using `docker-compose` with the appropriate environment variables. To see environment
variables used for configuration, check out the [sample environment](.env.sample).

### Running tests

Trovi runs a number of smoke tests based on the built-in Django test runner. To run tests, you can run
```shell
$ make test
```
or, you can run it manually using the [docker-compose file specifically intended for testing](tests-compose.yml).

## Publishing
Publish a new production image for Trovi using its git hash as the tag:
```shell
$ make publish
```
Tag the latest _local_ image of Trovi as latest and publish it:
```shell
$ make publish-latest
```
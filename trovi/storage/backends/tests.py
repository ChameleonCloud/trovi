import io
import random
import tarfile
from typing import IO
from uuid import uuid4

from requests import Response
from rest_framework import status
from rest_framework.reverse import reverse

from trovi.storage.backends.git import GitBackend

from trovi.api.tests import APITestCase
from util.test import version_don_quixote_1, version_don_quixote_2


class TestGitBackend(APITestCase):

    def setUp(self):
        pass


    def test_get_links_github(self):
        backend = GitBackend("git", "https://github.com/chameleoncloud/trovi@HEAD")
        actual = backend.get_links()
        expected = [
            {
                'headers': {},
                'method': 'GET',
                'protocol': 'http',
                'url': 'https://github.com/chameleoncloud/trovi/archive/HEAD.zip'
            },
            {
                'env': {},
                'protocol': 'git',
                'ref': 'HEAD',
                'remote': 'https://github.com/chameleoncloud/trovi'
            },
        ]
        for link in actual:
            del link["exp"]
        self.assertEqual(actual, expected)

    def test_get_links_opendev(self):
        backend = GitBackend("git", "https://opendev.org/openstack/blazar.git")
        actual = backend.get_links()
        expected = [
            {
                'env': {},
                'protocol': 'git',
                'ref': 'HEAD',
                'remote': 'https://opendev.org/openstack/blazar.git'
            },
        ]
        for link in actual:
            del link["exp"]
        self.assertEqual(actual, expected)


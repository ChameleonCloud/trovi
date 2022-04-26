from trovi.api.tests import APITest
from trovi.storage.backends.git import GitBackend


class TestGitBackend(APITest):
    def setUp(self):
        pass

    def test_get_links_github(self):
        backend = GitBackend(
            "git", "git", "https://github.com/chameleoncloud/trovi@HEAD"
        )
        actual = backend.get_links()
        expected = [
            {
                "headers": {},
                "method": "GET",
                "protocol": "http",
                "url": "https://github.com/chameleoncloud/trovi/archive/HEAD.zip",
            },
            {
                "env": {},
                "protocol": "git",
                "ref": "HEAD",
                "remote": "https://github.com/chameleoncloud/trovi",
            },
        ]
        for link in actual:
            del link["exp"]
        self.assertEqual(actual, expected)

    def test_get_links_opendev(self):
        backend = GitBackend("git", "git", "https://opendev.org/openstack/blazar.git")
        actual = backend.get_links()
        expected = [
            {
                "env": {},
                "protocol": "git",
                "ref": "HEAD",
                "remote": "https://opendev.org/openstack/blazar.git",
            },
        ]
        for link in actual:
            del link["exp"]
        self.assertEqual(actual, expected)

    def test_get_links_gitlab(self):
        backend = GitBackend("git", "git", "https://gitlab.com/gitlab-org/gitlab")
        actual = backend.get_links()
        expected = [
            {
                "headers": {},
                "method": "GET",
                "protocol": "http",
                "url": "https://gitlab.com/gitlab-org/gitlab/-/archive/HEAD/gitlab-HEAD.zip",
            },
            {
                "env": {},
                "protocol": "git",
                "ref": "HEAD",
                "remote": "https://gitlab.com/gitlab-org/gitlab",
            },
        ]
        for link in actual:
            del link["exp"]
        self.assertEqual(actual, expected)

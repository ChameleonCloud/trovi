import io
import os
import random
import tarfile
import uuid
from typing import IO
from unittest import skipIf
from urllib.parse import urlencode
from uuid import uuid4

from django.conf import settings
from django.test import TransactionTestCase, TestCase
from requests import Response
from rest_framework import status
from rest_framework.reverse import reverse

from trovi.api.tests import APITest
from trovi.common.tokens import JWT
from trovi.models import ArtifactVersionMigration, Artifact
from trovi.storage.urls import StoreContents, RetrieveContents
from util.test import version_don_quixote_1, version_don_quixote_2, artifact_don_quixote


class StorageTest(APITest):
    @staticmethod
    def get_test_data_gzip(n_bytes: int) -> IO:
        tar_buf = io.BytesIO()
        with tarfile.open(fileobj=tar_buf, mode="w:gz") as tar:
            file_buf = io.BytesIO(random.randbytes(n_bytes))
            tar.addfile(tarfile.TarInfo("rand_bytes"), fileobj=file_buf)

        tar_buf.seek(0)
        out = f"/tmp/trovi-test-{uuid4()}.tar.gz"
        with open(out, mode="wb") as f:
            # Test files are automatically cleaned up by the test runner
            f.write(tar_buf.getvalue())
        return open(out, mode="rb")

    @property
    def test_data_small(self) -> IO:
        """
        Returns a 256 byte test archive (before compression)
        """
        return self.get_test_data_gzip(256)

    @property
    def test_data_large(self) -> IO:
        """
        Returns a 10 MB test archive (before compression)
        """
        return self.get_test_data_gzip(10 * 1024 * 1024)

    def store_contents_path(self, backend: str = "chameleon") -> str:
        return self.authenticate_url(
            f"{reverse(StoreContents)}?backend={backend}",
            scopes=[JWT.Scopes.ARTIFACTS_WRITE],
        )

    def retrieve_contents_path(self, urn: str) -> str:
        return self.authenticate_url(
            f"{reverse(RetrieveContents)}?{urlencode({'urn': urn})}",
            scopes=[JWT.Scopes.ARTIFACTS_READ],
        )

    def store_content(
        self,
        data: IO,
        storage_backend: str = "chameleon",
        compression: str = "gz",
    ) -> Response:
        return self.client.post(
            self.store_contents_path(backend=storage_backend),
            content_type=f"application/tar+{compression}",
            data=data.read(),
            HTTP_CONTENT_DISPOSITION=f"attachment; filename={data.name}",
        )


class TestStoreContents(TestCase, StorageTest):
    content_uuids = set()

    def test_endpoint_works(self):
        try:
            base_response = self.client.post(self.store_contents_path())
            self.assertIsNotNone(base_response)
        except Exception as e:
            self.fail(str(e))

    def store_content_test(self, data: IO):
        response = self.store_content(data)

        self.assertEqual(
            response.status_code, status.HTTP_201_CREATED, msg=response.content
        )

        obj = response.json()
        self.assertIn("contents", obj, msg=obj)
        urn = obj["contents"]["urn"]
        self.assertIsInstance(urn, str)

        content_id = urn.split(":")[-1]
        self.content_uuids.add(content_id)

    def test_store_contents_small(self):
        self.store_content_test(self.test_data_small)

    def test_store_contents_large(self):
        self.store_content_test(self.test_data_large)

    def test_store_contents_invalid_format(self):
        # TODO
        pass

    def test_store_contents_size_too_large(self):
        # TODO
        pass

    def test_store_contents_size_too_small(self):
        # TODO
        pass


class TestRetrieveContents(TestCase, StorageTest):
    real_contents_urn = False

    def setUp(self):
        if not self.real_contents_urn:
            response1 = self.store_content(self.test_data_small)
            response2 = self.store_content(self.test_data_small)
            json1 = response1.json()
            json2 = response2.json()
            self.assertEqual(response1.status_code, status.HTTP_201_CREATED, msg=json1)
            self.assertEqual(response2.status_code, status.HTTP_201_CREATED, msg=json2)
            version_don_quixote_1.contents_urn = json1["contents"]["urn"]
            version_don_quixote_2.contents_urn = json2["contents"]["urn"]
            version_don_quixote_1.save()
            version_don_quixote_2.save()
            print(f"SETUP URN {version_don_quixote_1.contents_urn}")
            self.real_contents_urn = True

    def test_endpoint_works(self):
        try:
            base_response = self.client.get(self.retrieve_contents_path("placeholder"))
            self.assertIsNotNone(base_response)
        except Exception as e:
            self.fail(str(e))

    def test_retrieve_contents(self):
        response = self.client.get(
            self.retrieve_contents_path(version_don_quixote_1.contents_urn)
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.content)
        json = response.json()

        self.assertIn("contents", json)
        self.assertEqual(json["contents"]["urn"], version_don_quixote_1.contents_urn)

        self.assertIn("access_methods", json)
        for method in json["access_methods"]:
            self.assertIsInstance(method, dict)

    def test_retrieve_version_contents(self):
        response = self.client.get(
            self.authenticate_url(
                reverse(
                    "artifact-version-contents",
                    args=[artifact_don_quixote.uuid, version_don_quixote_1.slug],
                )
            )
        )

        as_json = response.json()

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=as_json)

        self.assertIn("contents", as_json, msg=as_json)
        self.assertEqual(
            as_json["contents"]["urn"], version_don_quixote_1.contents_urn, msg=as_json
        )

        self.assertIn("access_methods", as_json, msg=as_json)
        for method in as_json["access_methods"]:
            self.assertIsInstance(method, dict, msg=as_json)

    def test_retrieve_contents_artifact_not_found(self):
        fake_uuid = uuid.uuid4()
        while True:
            try:
                Artifact.objects.get(uuid=fake_uuid)
                fake_uuid = uuid.uuid4()
            except Artifact.DoesNotExist:
                break
        response = self.client.get(
            self.authenticate_url(
                reverse(
                    "artifact-version-contents",
                    args=[fake_uuid, version_don_quixote_1.slug],
                )
            )
        )
        self.assertEqual(
            response.status_code, status.HTTP_404_NOT_FOUND, msg=response.content
        )

    def test_retrive_contents_version_not_found(self):
        response = self.client.get(
            self.authenticate_url(
                reverse(
                    "artifact-version-contents",
                    args=[artifact_don_quixote.uuid, "retrive-contents-not-found-slug"],
                )
            )
        )
        self.assertEqual(
            response.status_code, status.HTTP_404_NOT_FOUND, msg=response.content
        )

    def test_retrive_version_contents_private(self):
        artifact_don_quixote.refresh_from_db()
        artifact_don_quixote.visibility = Artifact.Visibility.PRIVATE
        artifact_don_quixote.save()

        response = self.client.get(
            self.authenticate_url(
                reverse(
                    "artifact-version-contents",
                    args=[artifact_don_quixote.uuid, version_don_quixote_1.slug],
                )
            )
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.content)

    def test_retrieve_version_contents_private_no_permission(self):
        artifact_don_quixote.refresh_from_db()
        artifact_don_quixote.visibility = Artifact.Visibility.PRIVATE
        for role in artifact_don_quixote.roles.all():
            role.delete()
        artifact_don_quixote.save()

        response = self.client.get(
            self.authenticate_url(
                reverse(
                    "artifact-version-contents",
                    args=[artifact_don_quixote.uuid, version_don_quixote_1.slug],
                )
            )
        )
        self.assertEqual(
            response.status_code, status.HTTP_403_FORBIDDEN, msg=response.content
        )

    def test_retrieve_contents_access_methods(self):
        # TODO
        pass

    def test_invalid_storage_backend(self):
        # TODO
        pass


@skipIf(
    settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3",
    "Skipping Version Migration test; SQLite has difficulties with transactions.",
)
class TestMigrateArtifactVersion(TransactionTestCase, StorageTest):
    """
    Since migrations run in a separate thread, this test class needs to be
    a little special. The base ``TestCase`` class runs all tests inside a transaction
    so that when they end, changes to the database are rolled back. This lets you
    make whatever changes in the test case and still have fresh state for every test.
    However, this transaction locks the database from other threads, so using this
    type of test case here results in an infinite hang. Instead, we use
    a ``TransactionTestCase``, which is designed to test transactions i.e. does not hold
    its own transaction.

    Special care needs to be directed to two things:
    1. Only one test can live inside this class. It will fail if the ``setUp`` method
       is run more than once.
    2. Significant changes inside these tests should be avoided, as the state will be
       retained into other tests.
    """

    real_contents_urn = False

    def setUp(self):
        if not self.real_contents_urn:
            response1 = self.store_content(self.test_data_small)
            response2 = self.store_content(self.test_data_small)
            json1 = response1.json()
            json2 = response2.json()
            self.assertEqual(response1.status_code, status.HTTP_201_CREATED, msg=json1)
            self.assertEqual(response2.status_code, status.HTTP_201_CREATED, msg=json2)
            version_don_quixote_1.contents_urn = json1["contents"]["urn"]
            version_don_quixote_2.contents_urn = json2["contents"]["urn"]
            version_don_quixote_1.save()
            version_don_quixote_2.save()
            print(f"SETUP URN {version_don_quixote_1.contents_urn}")
            self.real_contents_urn = True

    def test_migrate_storage(self):
        artifact_don_quixote.refresh_from_db()
        artifact_don_quixote.owner_urn = f"urn:trovi:user:chameleon:{os.getenv('CHAMELEON_KEYCLOAK_TEST_USER_USERNAME')}"
        artifact_don_quixote.save()
        response = self.client.post(
            self.migrate_artifact_version_path(
                artifact_don_quixote.uuid, version_don_quixote_1.slug
            ),
            content_type="application/json",
            data={"backend": "zenodo"},
        )

        as_json = response.json()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=as_json)

        migration = version_don_quixote_1.migrations.first()
        migration_status = ArtifactVersionMigration.MigrationStatus
        self.assertNotEqual(migration.status, migration_status.ERROR)
        while migration.status != migration_status.SUCCESS:
            # This probably deserves a better check.
            migration.refresh_from_db()
            self.assertNotEqual(
                migration.status, migration_status.ERROR, msg=migration.message
            )

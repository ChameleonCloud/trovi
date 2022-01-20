import io
import random
import tarfile
from typing import IO
from uuid import uuid4

from requests import Response
from rest_framework import status
from rest_framework.reverse import reverse

from trovi.api.tests import APITestCase
from trovi.storage.urls import StoreContents, RetrieveContents
from util.test import version_don_quixote_1, version_don_quixote_2


class StorageTestCase(APITestCase):
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
        Returns a 256 byte test archive
        """
        return self.get_test_data_gzip(256)

    @property
    def test_data_large(self) -> IO:
        """
        Returns a 3 MB test archive
        """
        return self.get_test_data_gzip(3 * 1024 * 1024)

    @staticmethod
    def store_contents_path(backend: str = "chameleon") -> str:
        return f"{reverse(StoreContents)}?backend={backend}"

    @staticmethod
    def retrieve_contents_path(urn: str) -> str:
        return reverse(RetrieveContents, kwargs={"urn": urn})

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


class TestStoreContents(StorageTestCase):

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


class TestRetrieveContents(StorageTestCase):
    real_contents_urn = False

    def setUp(self):
        if not self.real_contents_urn:
            response1 = self.store_content(self.test_data_small)
            response2 = self.store_content(self.test_data_small)
            version_don_quixote_1.contents_urn = response1.json()["contents"]["urn"]
            version_don_quixote_2.contents_urn = response2.json()["contents"]["urn"]
            version_don_quixote_1.save()
            version_don_quixote_2.save()
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

    def test_retrieve_contents_not_found(self):
        # TODO
        pass

    def test_retrieve_contents_access_methods(self):
        # TODO
        pass

    def test_invalid_storage_backend(self):
        # TODO
        pass

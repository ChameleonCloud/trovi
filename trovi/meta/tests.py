import json

from rest_framework import status
from rest_framework.reverse import reverse

from trovi.api.tests import APITestCase
from trovi.common.tokens import JWT
from trovi.models import ArtifactTag

TAGS_PATH = reverse("Tags")


class TestListTags(APITestCase):
    def test_endpoint_works(self):
        try:
            base_response = self.client.get(self.authenticate_url(TAGS_PATH))
            self.assertIsNotNone(base_response)
        except Exception as e:
            self.fail(str(e))

    def test_response_format(self):
        response = self.client.get(self.authenticate_url(TAGS_PATH))
        as_json = response.json()

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=as_json)

        self.assertIn("tags", as_json)

        self.assertListEqual(
            [tag["tag"] for tag in as_json["tags"]],
            [tag.tag for tag in ArtifactTag.objects.order_by("tag")],
        )


class TestCreateTag(APITestCase):
    def test_endpoint_works(self):
        try:
            base_response = self.client.post(self.authenticate_url(TAGS_PATH))
            self.assertIsNotNone(base_response)
        except Exception as e:
            self.fail(str(e))

    def test_permission(self):
        # Confirm that writing tags is only possible by an admin
        new_tag = {"tag": "ABCDEFG"}
        response = self.client.post(
            self.authenticate_url(TAGS_PATH, [JWT.Scopes.ARTIFACTS_WRITE]),
            content_type="application/json",
            data=json.dumps(new_tag),
        )

        # With any permissions except admin, we should not be allowed to write tags
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            ArtifactTag.objects.filter(tag__iexact=new_tag["tag"]).count(),
            0,
            "Found new tag in database with bad permissions",
        )

        response = self.client.post(
            self.authenticate_url(TAGS_PATH, [JWT.Scopes.TROVI_ADMIN]),
            content_type="application/json",
            data=json.dumps(new_tag),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        self.assertGreater(
            ArtifactTag.objects.filter(tag__iexact=new_tag["tag"]).count(),
            0,
            "CreateTag did not save tag to database",
        )

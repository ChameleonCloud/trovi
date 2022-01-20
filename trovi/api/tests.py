import json

from django.db import models
from django.http import JsonResponse
from django.test import TestCase
from rest_framework import serializers, status
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.reverse import reverse

from trovi.api.serializers import ArtifactSerializer
from trovi.api.urls import ListArtifact, GetArtifact, CreateArtifact, UpdateArtifact
from trovi.models import (
    Artifact,
    ArtifactTag,
)
from util.test import DummyArtifact, artifact_don_quixote


class APITestCase(TestCase):
    renderer = JSONRenderer()
    maxDiff = None
    tests_run = 0

    @staticmethod
    def list_artifact_path():
        return reverse(ListArtifact)

    @staticmethod
    def get_artifact_path(artifact_uuid: str):
        return reverse(GetArtifact, args=[artifact_uuid])

    @staticmethod
    def create_artifact_path():
        return reverse(CreateArtifact)

    @staticmethod
    def update_artifact_path(artifact_uuid: str):
        return reverse(UpdateArtifact, args=[artifact_uuid])

    def assertAPIModelContentEqual(self, actual: models.Model, expected: models.Model):
        self.assertJSONEqual(
            json.dumps(serializers.ModelSerializer(actual).data),
            json.dumps(serializers.ModelSerializer(expected).data),
        )

    def assertAPIResponseEqual(self, response: dict, model: serializers.Serializer):
        rendered = self.renderer.render(JsonResponse(model.data).content)
        as_dict = json.loads(json.loads(rendered))
        self.assertDictContainsSubset(response, as_dict)

    def assertDictContainsSubset(self, d1: dict, d2: dict, msg: str = None):
        """
        Deeply asserts that one dictionary is a subset of the other.

        This function is definitely fallible, but the hope is that other schema tests
        can make up for it's potential points of failure.
        """
        smaller = min((d1, d2), key=len)
        larger = max((d1, d2), key=len)

        for key, small_value in smaller.items():
            large_value = larger[key]
            if isinstance(small_value, dict):
                self.assertDictContainsSubset(small_value, large_value)
            elif isinstance(small_value, list):
                small_dict = {i: o for i, o in enumerate(small_value)}
                large_dict = {i: o for i, o in enumerate(large_value)}
                self.assertDictContainsSubset(small_dict, large_dict)
            else:
                self.assertEqual(small_value, large_value)


class TestListArtifacts(APITestCase):
    def test_endpoint_works(self):
        try:
            base_response = self.client.get(self.list_artifact_path())
            self.assertIsNotNone(base_response)
        except Exception as e:
            self.fail(str(e))

    def test_response_format(self):
        response = self.client.get(self.list_artifact_path())
        as_json = json.loads(response.content)

        self.assertIn("artifacts", as_json)
        self.assertIn("next", as_json)
        self.assertIn("after", as_json["next"])
        self.assertIn("limit", as_json["next"])

        self.assertIsInstance(as_json["artifacts"], list)
        for artifact in as_json["artifacts"]:
            self.assertIsInstance(artifact, dict)
        # After parameter should be null in un-paginated responses,
        # but limit is always equal to the amount of returned artifacts
        self.assertIsNone(as_json["next"]["after"])
        self.assertIsInstance(as_json["next"]["limit"], int)

    def test_list_length(self):
        response = self.client.get(self.list_artifact_path())
        as_json = json.loads(response.content)

        visible_objects_count = Artifact.objects.filter(
            visibility=Artifact.Visibility.PUBLIC
        ).count()
        self.assertEqual(visible_objects_count, len(as_json["artifacts"]))
        self.assertEqual(visible_objects_count, as_json["next"]["limit"])

    def test_visibility(self):
        private_artifacts = {
            str(a.uuid)
            for a in Artifact.objects.filter(visibility=Artifact.Visibility.PRIVATE)
        }
        response = self.client.get(self.list_artifact_path())
        as_json = json.loads(response.content)

        for artifact in as_json["artifacts"]:
            self.assertNotIn(artifact["id"], private_artifacts)

    def test_url_parameters(self):
        # TODO
        pass
        self.client.get(
            self.list_artifact_path() + f"?after={artifact_don_quixote.uuid}"
        )


class TestListArtifactsEmpty(TestListArtifacts):
    @classmethod
    def setUpClass(cls):
        TestCase.setUpClass()
        Artifact.objects.all().delete()


class TestGetArtifact(APITestCase):
    def test_get_artifact(self):
        # TODO verify random data
        response = self.client.get(self.get_artifact_path(artifact_don_quixote.uuid))
        as_json = json.loads(response.content)

        self.assertAPIResponseEqual(as_json, ArtifactSerializer(artifact_don_quixote))

    def test_get_private_artifact(self):
        # TODO
        pass

    def test_get_private_artifact_for_user(self):
        # TODO
        pass

    def test_get_missing_artifact(self):
        # TODO
        pass

    def test_sharing_key(self):
        # TODO
        pass


class TestCreateArtifact(APITestCase):
    allowed_tag1 = "!!CreateArtifactTag1!!"
    allowed_tag2 = "!!CreateArtifactTag2!!"

    @classmethod
    def setUpClass(cls):
        super(TestCreateArtifact, cls).setUpClass()
        ArtifactTag.objects.create(tag=cls.allowed_tag1)
        ArtifactTag.objects.create(tag=cls.allowed_tag2)

    def test_create_artifact_all_params(self):
        new_artifact = {
            "title": "Testing CreateObject",
            "short_description": "Testing out the CreateArtifact API Endpoint.",
            "long_description": "Well, it sure is a fine day out here to create "
            "some unit tests for the Trovi CreateArtifact API endpoint. "
            "Yes siree, this sure is a mighty fine endpoint, "
            "if I do say so myself.",
            "tags": [],
            "authors": [
                {
                    "full_name": "Dr. Leon Cloudly",
                    "affiliation": "Chameleon Cloud",
                    "email": "no-reply@chameleoncloud.org",
                },
                {
                    "full_name": "Dr. RIC FABulous",
                    "affiliation": "FABRIC Testbed",
                    "email": "no-reply@fabric-testbed.net",
                },
            ],
            "visibility": "public",
            "linked_projects": [
                "urn:chameleon:CH-1111",
                "urn:chameleon:CH-2222",
            ],
            "reproducibility": {"enable_requests": True, "access_hours": 3},
            "version": {
                "contents": {
                    "urn": "urn:contents:chameleon:108beeac-564f-4030-b126-ec4d903e680e"
                },
                "links": [
                    {
                        "label": "Training data",
                        "urn": "urn:dataset:globus:"
                        "979a1221-8c42-41bf-bb08-4a16ed981447:"
                        "/training_set",
                    },
                    {
                        "label": "Our training image",
                        "urn": "urn:disk-image:chameleon:CHI@TACC:"
                        "fd13fbc0-2d53-4084-b348-3dbd60cdc5e1",
                    },
                ],
            },
        }

        response = self.client.post(
            self.create_artifact_path(),
            content_type="application/json",
            data=json.dumps(new_artifact),
        )

        # If the request is bad, sometimes a tuple is returned
        self.assertIsInstance(response, Response)
        response_body = json.loads(response.content)
        self.assertEqual(
            response.status_code, status.HTTP_201_CREATED, msg=response_body
        )

        # TODO test that automatic fields are created properly
        model = Artifact.objects.get(uuid=response_body["id"])
        new_artifact["versions"] = [new_artifact.pop("version")]
        self.assertAPIResponseEqual(new_artifact, ArtifactSerializer(model))

    def test_request_schema(self):
        # TODO
        pass

    def test_cannot_create_tags(self):
        # TODO
        pass

    def test_get_or_create_project(self):
        # TODO
        pass

    def test_create_body_field_matrix(self):
        # TODO test object creation with all different combinations
        #  of present/missing fields
        pass


class TestUpdateArtifact(APITestCase):
    def test_update_artifact(self):
        # Ensures that the update endpoint is functioning
        # Extensive testing is not needed here, as most of the logic is
        # handled by json-patch
        artifact_don_quixote.refresh_from_db()
        old_donq_as_json = ArtifactSerializer(artifact_don_quixote).data

        patch = [
            {
                "op": "replace",
                "path": "/short_description",
                "value": "I've been patched!!!",
            },
            {
                "op": "remove",
                "path": "/reproducibility/access_hours",
            },
            {
                "op": "move",
                "from": "/long_description",
                "path": "/title",
            },
        ]

        response = self.client.patch(
            self.update_artifact_path(artifact_don_quixote.uuid),
            content_type="application/json",
            data=patch,
        )

        # If the request is bad, sometimes a tuple is returned
        self.assertIsInstance(response, Response)
        new_donq_as_json = json.loads(response.content)
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=new_donq_as_json)
        new_donq = DummyArtifact(**new_donq_as_json)

        # Test that the intended fields changed
        diff_msg = f"{old_donq_as_json=} {new_donq_as_json=}"
        new_description = new_donq.short_description
        self.assertEqual(new_description, patch[0]["value"], msg=diff_msg)
        self.assertNotEqual(
            new_description, artifact_don_quixote.short_description, msg=diff_msg
        )

        new_access_hours = new_donq.repro_access_hours
        self.assertIsNone(new_access_hours)

        self.assertIsNone(new_donq.long_description, msg=diff_msg)
        self.assertEqual(new_donq.title, artifact_don_quixote.long_description)

        # Test that nothing unexpected changed
        new_donq_as_json.pop("updated_at")
        old_donq_as_json.pop("updated_at")
        new_donq_as_json.pop("short_description")
        old_donq_as_json.pop("short_description")
        new_donq_as_json.pop("long_description")
        old_donq_as_json.pop("long_description")
        new_donq_as_json.pop("reproducibility")
        old_donq_as_json.pop("reproducibility")
        new_donq_as_json.pop("title")
        old_donq_as_json.pop("title")
        self.assertDictEqual(new_donq_as_json, old_donq_as_json)

    def test_update_artifact_abilities(self):
        # TODO ensure that restrictions of certain operations on certain fields are met
        pass

    def test_update_artifact_updated_automatic_fields(self):
        # TODO test fields that should be updated automatically by a PATCH
        pass

    def test_update_sharing_key(self):
        # TODO ensure that a delete actually rotates the sharing key
        pass

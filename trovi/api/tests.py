import json
import os
import random
import uuid

from django.db import models
from django.http import JsonResponse
from django.test import TestCase
from rest_framework import serializers, status
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.reverse import reverse

from trovi.api.serializers import ArtifactSerializer, ArtifactVersionSerializer
from trovi.api.urls import (
    ListArtifact,
    GetArtifact,
    CreateArtifact,
    UpdateArtifact,
    CreateArtifactVersion,
    DeleteArtifactVersion,
)
from trovi.auth import providers
from trovi.common.tokens import TokenTypes, JWT
from trovi.models import (
    Artifact,
    ArtifactTag,
    ArtifactVersion,
    ArtifactAuthor,
)
from util.test import (
    DummyArtifact,
    artifact_don_quixote,
    version_don_quixote_1,
    version_don_quixote_2,
)


class APITestCase(TestCase):
    renderer = JSONRenderer()
    maxDiff = None

    def get_test_token(self, scopes: list[JWT.Scopes] = None) -> str:
        # TODO have each test run once per provider
        keycloak = None
        for _, provider in providers.get_clients().items():
            if provider.get_name() == "CHAMELEON_KEYCLOAK":
                keycloak = provider
                break
        if not keycloak:
            raise ValueError("No keycloak IdP for testing.")
        provider_name = keycloak.get_name()
        test_username = os.getenv(f"{provider_name}_TEST_USER_USERNAME")
        test_password = os.getenv(f"{provider_name}_TEST_USER_PASSWORD")
        test_client_id = os.getenv(f"{provider_name}_TEST_CLIENT_ID")
        test_client_secret = os.getenv(f"{provider_name}_TEST_CLIENT_SECRET")

        valid_token = keycloak.get_user_token(
            test_username, test_password, test_client_id, test_client_secret
        )

        requesting_scopes = scopes if scopes else [JWT.Scopes.ARTIFACTS_READ]

        response = self.client.post(
            reverse("TokenGrant"),
            content_type="application/json",
            data={
                "grant_type": "token_exchange",
                "subject_token": valid_token,
                "subject_token_type": TokenTypes.ACCESS_TOKEN_TYPE.value,
                "scope": " ".join(map(lambda s: s.value, requesting_scopes)),
            },
        )

        return response.json()["access_token"]

    def authenticate_url(self, url: str, scopes: list[JWT.Scopes] = None) -> str:
        return (
            url
            + ("?" if "?" not in url else "&")
            + f"access_token={self.get_test_token(scopes=scopes)}"
        )

    def list_artifact_path(self):
        return self.authenticate_url(reverse(ListArtifact))

    def get_artifact_path(self, artifact_uuid: str):
        return self.authenticate_url(reverse(GetArtifact, args=[artifact_uuid]))

    def create_artifact_path(self):
        return self.authenticate_url(
            reverse(CreateArtifact), scopes=[JWT.Scopes.ARTIFACTS_WRITE]
        )

    def update_artifact_path(self, artifact_uuid: str):
        return self.authenticate_url(
            reverse(UpdateArtifact, args=[artifact_uuid]),
            scopes=[JWT.Scopes.ARTIFACTS_READ, JWT.Scopes.ARTIFACTS_WRITE],
        )

    def create_artifact_version_path(self, artifact_uuid: str):
        return self.authenticate_url(
            reverse(
                CreateArtifactVersion,
                args=[artifact_uuid],
                # This tests that the user cannot overwrite the parent artifact ID
            )
            + "?parent_lookup_artifact=foo",
            scopes=[JWT.Scopes.ARTIFACTS_WRITE],
        )

    def delete_artifact_version_path(self, artifact_uuid: str, version_slug: str):
        return self.authenticate_url(
            reverse(DeleteArtifactVersion, args=[artifact_uuid, version_slug]),
            scopes=[JWT.Scopes.ARTIFACTS_WRITE],
        )

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

    def test_sharing_key(self):
        # TODO
        pass

    def test_private_artifacts_for_user(self):
        # TODO
        pass


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

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=as_json)

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

    def test_create_no_write_scope(self):
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
        # Cheekily add the test user as an author for Don Quixote,
        # so that we may write to it
        # TODO will eventually have to add all test users as authors
        artifact_don_quixote.authors.add(
            ArtifactAuthor.objects.create(
                full_name="Trovi Tester",
                email=os.getenv("CHAMELEON_KEYCLOAK_TEST_USER_USERNAME"),
            )
        )

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

    def test_update_artifact_no_write_scope(self):
        # TODO
        pass

    def test_update_artifact_not_author(self):
        # TODO
        pass


class TestCreateArtifactVersion(APITestCase):
    example_version = {
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
    }

    def test_endpoint_works(self):
        try:
            base_response = self.client.post(
                self.create_artifact_version_path(artifact_don_quixote.uuid),
                content_type="application/json",
                data={},
            )
            self.assertIsNotNone(base_response)
        except Exception as e:
            self.fail(str(e))

    def test_create_artifact_version(self):
        artifact_don_quixote.refresh_from_db()

        response = self.client.post(
            self.create_artifact_version_path(artifact_don_quixote.uuid),
            content_type="application/json",
            data=self.example_version,
        )

        self.assertEqual(
            response.status_code, status.HTTP_201_CREATED, msg=response.content
        )
        response_body = response.json()

        model = ArtifactVersion.objects.get(
            contents_urn=response_body["contents"]["urn"]
        )
        self.assertAPIResponseEqual(response_body, ArtifactVersionSerializer(model))
        self.assertEqual(artifact_don_quixote.uuid, model.artifact.uuid)
        self.assertIn(model, artifact_don_quixote.versions.all())

    def test_link_to_non_existent_artifact(self):
        fake_uuid = uuid.uuid4()
        while True:
            try:
                Artifact.objects.get(uuid=fake_uuid)
                fake_uuid = uuid.uuid4()
            except Artifact.DoesNotExist:
                break
        response = self.client.post(
            self.create_artifact_version_path(str(fake_uuid)),
            content_type="application/json",
            data=self.example_version,
        )
        self.assertEqual(
            response.status_code, status.HTTP_404_NOT_FOUND, msg=response.content
        )

    def test_non_unique_artifact_contents(self):
        example = self.example_version.copy()
        example["contents"]["urn"] = version_don_quixote_1.contents_urn

        # Test against same artifact
        response_1 = self.client.post(
            self.create_artifact_version_path(artifact_don_quixote.uuid),
            content_type="application/json",
            data=example,
        )

        self.assertEqual(
            response_1.status_code, status.HTTP_409_CONFLICT, msg=response_1.content
        )

        # Test against different artifact
        random_artifact = random.choice(Artifact.objects.all())
        response_2 = self.client.post(
            self.create_artifact_version_path(random_artifact.uuid),
            content_type="application/json",
            data=example,
        )

        self.assertEqual(
            response_2.status_code, status.HTTP_409_CONFLICT, msg=response_2.content
        )

    def test_create_artifact_version_no_write_scope(self):
        # TODO
        pass


class TestDeleteArtifactVersion(APITestCase):
    def test_endpoint_works(self):
        try:
            base_response = self.client.delete(
                self.delete_artifact_version_path(str(artifact_don_quixote.uuid), "foo")
            )
            self.assertIsNotNone(base_response)
        except Exception as e:
            self.fail(e)

    def test_delete_artifact_version(self):
        artifact_don_quixote.authors.add(
            ArtifactAuthor.objects.create(
                full_name="Trovi Tester",
                email=os.getenv("CHAMELEON_KEYCLOAK_TEST_USER_USERNAME"),
            )
        )
        for version in (version_don_quixote_1, version_don_quixote_2):
            response = self.client.delete(
                self.delete_artifact_version_path(
                    str(artifact_don_quixote.uuid), version.slug
                )
            )
            self.assertIsNotNone(response)

            self.assertEqual(
                response.status_code, status.HTTP_204_NO_CONTENT, msg=response.content
            )

            # Ensure version has been deleted
            exists = True
            try:
                ArtifactVersion.objects.get(contents_urn=version.contents_urn)
            except ArtifactVersion.DoesNotExist:
                exists = False
            finally:
                self.assertFalse(exists)

            # Ensure version is no longer associated with artifact
            self.assertNotIn(version, version.artifact.versions.all())

        self.assertEqual(0, artifact_don_quixote.versions.count())

    def test_delete_version_no_artifact(self):
        fake_uuid = uuid.uuid4()
        while True:
            try:
                Artifact.objects.get(uuid=fake_uuid)
                fake_uuid = uuid.uuid4()
            except Artifact.DoesNotExist:
                break
        response = self.client.delete(
            self.delete_artifact_version_path(
                str(fake_uuid), version_don_quixote_1.slug
            )
        )
        self.assertEqual(
            response.status_code, status.HTTP_404_NOT_FOUND, msg=response.content
        )

    def test_delete_artifact_version_no_write_scope(self):
        # TODO
        pass

    def test_delete_artifact_version_not_author(self):
        # TODO
        pass

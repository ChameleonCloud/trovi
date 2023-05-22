import copy
import json
import os
import random
import uuid

from django.conf import settings
from django.db import models
from django.http import JsonResponse
from django.test import TestCase, override_settings, SimpleTestCase
from django.utils import timezone
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
    IncrArtifactVersionMetrics,
    MigrateArtifactVersion,
    AssignArtifactRole,
    UnassignArtifactRole,
)
from trovi.auth.providers import get_client_by_name
from trovi.common.tokens import TokenTypes, JWT
from trovi.models import (
    Artifact,
    ArtifactTag,
    ArtifactVersion,
    ArtifactRole,
)
from util.decorators import timed_lru_cache
from util.test import (
    artifact_don_quixote,
    version_don_quixote_1,
    version_don_quixote_2,
    make_admin,
    role_don_quixote_don,
    role_don_quixote_admin,
)
from util.types import DummyRequest


class APITest(SimpleTestCase):
    renderer = JSONRenderer()
    maxDiff = None

    def get_test_context(self):
        request = DummyRequest(
            data={}, auth=JWT.from_jws(self.get_test_token()), query_params={}
        )
        return {"request": request, "view": None}

    @timed_lru_cache(timeout=settings.AUTH_TROVI_TOKEN_LIFESPAN_SECONDS)
    def get_test_token(self, scope: str = None) -> str:
        provider_name = "CHAMELEON_KEYCLOAK"
        keycloak = get_client_by_name(provider_name)
        test_username = os.getenv(f"{provider_name}_TEST_USER_USERNAME")
        test_password = os.getenv(f"{provider_name}_TEST_USER_PASSWORD")
        test_client_id = os.getenv(f"{provider_name}_TEST_CLIENT_ID")
        test_client_secret = os.getenv(f"{provider_name}_TEST_CLIENT_SECRET")

        valid_token = keycloak.get_user_token(
            test_username, test_password, test_client_id, test_client_secret
        )

        requesting_scope = scope if scope else JWT.Scopes.ARTIFACTS_READ

        response = self.client.post(
            reverse("TokenGrant"),
            content_type="application/json",
            data={
                "grant_type": "token_exchange",
                "subject_token": valid_token,
                "subject_token_type": TokenTypes.JWT_TOKEN_TYPE.value,
                "scope": requesting_scope,
            },
        )

        body = response.json()

        if response.status_code != status.HTTP_201_CREATED:
            self.fail(json.dumps(body))

        return response.json()["access_token"]

    def authenticate_url(self, url: str, scopes: list[JWT.Scopes] = None) -> str:
        scopes = scopes or [JWT.Scopes.ARTIFACTS_READ]
        return (
            url
            + ("?" if "?" not in url else "&")
            + f"access_token={self.get_test_token(scope=' '.join(scopes))}"
        )

    def list_artifact_path(self):
        return self.authenticate_url(reverse(ListArtifact))

    def get_artifact_path(self, artifact_uuid: str):
        return self.authenticate_url(reverse(GetArtifact, args=[artifact_uuid]))

    def create_artifact_path(self, is_admin=False):
        scope = [JWT.Scopes.ARTIFACTS_WRITE]
        if is_admin:
            scope.append(JWT.Scopes.TROVI_ADMIN)
        return self.authenticate_url(reverse(CreateArtifact), scopes=scope)

    def update_artifact_path(self, artifact_uuid: str):
        return self.authenticate_url(
            reverse(UpdateArtifact, args=[artifact_uuid]),
            scopes=[
                JWT.Scopes.ARTIFACTS_READ,
                JWT.Scopes.ARTIFACTS_WRITE,
                JWT.Scopes.TROVI_ADMIN,
            ],
        )

    def create_artifact_version_path(self, artifact_uuid: str):
        return self.authenticate_url(
            reverse(
                CreateArtifactVersion,
                args=[artifact_uuid],
            )
            # This tests that the user cannot overwrite the parent artifact ID
            + "?parent_lookup_artifact=foo",
            scopes=[JWT.Scopes.ARTIFACTS_WRITE],
        )

    def delete_artifact_version_path(self, artifact_uuid: str, version_slug: str):
        return self.authenticate_url(
            reverse(DeleteArtifactVersion, args=[artifact_uuid, version_slug]),
            scopes=[JWT.Scopes.ARTIFACTS_WRITE],
        )

    def incr_artifact_version_metrics_path(
        self, artifact_uuid: str, version_slug: str, metric: str, amount: int = None
    ):
        if amount:
            amount_arg = f"&amount={amount}"
        else:
            amount_arg = ""
        return self.authenticate_url(
            f"{reverse(IncrArtifactVersionMetrics, args=[artifact_uuid, version_slug])}"
            f"?metric={metric}&origin={self.get_test_token()}{amount_arg}",
            scopes=[JWT.Scopes.ARTIFACTS_WRITE_METRICS],
        )

    def migrate_artifact_version_path(self, artifact_uuid: str, version_slug: str):
        return self.authenticate_url(
            reverse(MigrateArtifactVersion, args=[artifact_uuid, version_slug]),
            scopes=[JWT.Scopes.ARTIFACTS_WRITE],
        )

    def assign_artifact_role_path(self, artifact_uuid: str) -> str:
        return self.authenticate_url(
            reverse(AssignArtifactRole, args=[artifact_uuid]),
            scopes=[JWT.Scopes.ARTIFACTS_WRITE],
        )

    def unassign_artifact_role_path(
        self, artifact_uuid: str, user: str, role: ArtifactRole.RoleType
    ) -> str:
        return self.authenticate_url(
            reverse(
                UnassignArtifactRole,
                args=[artifact_uuid],
            )
            + f"?user={user}&role={role}",
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
        self.assertDictContainsSubset(
            response, as_dict, f"{rendered}\n-----------\n{as_dict}"
        )

    def assertDictContainsSubset(self, d1: dict, d2: dict, msg: str = None):
        """
        Deeply asserts that one dictionary is a subset of the other.

        This function is definitely fallible, but the hope is that other schema tests
        can make up for it's potential points of failure.
        """
        smaller = min((d1, d2), key=len)
        larger = max((d1, d2), key=len)

        for key, small_value in smaller.items():
            self.assertIn(key, larger)
            large_value = larger[key]
            if isinstance(small_value, dict):
                self.assertDictContainsSubset(small_value, large_value, msg=msg)
            elif isinstance(small_value, list):
                small_dict = {i: o for i, o in enumerate(small_value)}
                large_dict = {i: o for i, o in enumerate(large_value)}
                self.assertDictContainsSubset(small_dict, large_dict, msg=msg)
            else:
                self.assertEqual(small_value, large_value, msg=msg)


class TestListArtifacts(TestCase, APITest):
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

        public = Artifact.objects.filter(visibility=Artifact.Visibility.PUBLIC)
        has_doi = Artifact.objects.filter(versions__contents_urn__contains="zenodo")
        visible_objects_count = public.union(has_doi).count()
        self.assertEqual(visible_objects_count, len(as_json["artifacts"]), as_json)
        self.assertEqual(visible_objects_count, as_json["next"]["limit"], as_json)

    def test_private_doi(self):
        # This test is skipped for the empty tests
        if Artifact.objects.count() == 0:
            return
        private_artifacts = {
            str(a.uuid)
            for a in Artifact.objects.filter(visibility=Artifact.Visibility.PRIVATE)
        }
        # Assure that there is at least one private artifact without a DOI
        Artifact.objects.get(uuid=next(iter(private_artifacts), None)).versions.filter(
            contents_urn__contains="zenodo"
        ).delete()
        response = self.client.get(self.list_artifact_path())
        as_json = json.loads(response.content)

        for artifact in as_json["artifacts"]:
            if not any("zenodo" in v["contents"]["urn"] for v in artifact["versions"]):
                self.assertNotIn(artifact["uuid"], private_artifacts)

    def test_url_parameters(self):
        def after(url: str) -> str:
            return f"{url}&after={artifact_don_quixote.uuid}"

        def sort(url: str, by: str) -> str:
            return f"{url}&sort_by={by}"

        def test_after(body: dict[str, list[dict]], artifact: Artifact):
            self.assertEqual(str(artifact.uuid), body["artifacts"][0]["uuid"])

        def test_sorted(body: dict[str, list[dict]], by: str):
            artifact_models = Artifact.objects.filter(
                uuid__in={a["uuid"] for a in body["artifacts"]}
            )
            if by == "date":
                # Our ground truth is a sorted list of all the IDs
                # for every artifact returned by the API call
                # String timestamps are not precise enough to test sorting, and have too
                # many duplicate values. The order of the IDs sorted by creation time
                # is a more accurate representation.
                base = [
                    str(a.uuid)
                    for a in sorted(
                        artifact_models.all(), reverse=True, key=lambda a: a.created_at
                    )
                ]
                test = [a["uuid"] for a in body["artifacts"]]
            elif by == "access_count":
                # Our ground truth is a sorted list of the sums of all the versions'
                # access_counts for each artifact returned by the API call
                # The access_counts have the potential for repeat values which do not
                # guarantee that the artifacts with the same value will be sorted in
                # the same order. As such, we check against the sorted access_counts
                # themselves
                base = list(
                    a.access_count for a in artifact_models.order_by("-access_count")
                )
                test = [
                    Artifact.objects.get(uuid=a["uuid"]).access_count
                    for a in body["artifacts"]
                ]
            else:
                base = []
                test = [1]

            self.assertListEqual(base, test, f"Improperly sorted for key {by}")

        # Test paging
        response = self.client.get(after(self.list_artifact_path()))
        body = response.json()
        if Artifact.objects.count() > 0:
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            test_after(body, artifact_don_quixote)
        else:
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Test sorting
        for sort_param in ("date", "access_count"):
            response = self.client.get(sort(self.list_artifact_path(), sort_param))
            body = response.json()
            if Artifact.objects.count() > 0:
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                test_sorted(body, sort_param)
            else:
                # We don't use 'after' here so there should be no 404
                self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test sharing key
        # This test is skipped for the empty list
        if Artifact.objects.count() == 0:
            return
        a_private_artifact = Artifact.objects.filter(
            visibility=Artifact.Visibility.PRIVATE
        ).first()
        a_private_artifact.versions.filter(contents_urn__contains="zenodo").delete()
        if not a_private_artifact:
            a_private_artifact = Artifact()
        for sort_param in ("date", "access_count"):
            response = self.client.get(
                f"{sort(self.list_artifact_path(), sort_param)}"
                f"&sharing_key={a_private_artifact.sharing_key}"
            )
            body = response.json()
            if len(body.get("artifacts", [])) > 0:
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                test_sorted(body, sort_param)
                privs = {
                    a["uuid"] for a in body["artifacts"] if a["visibility"] == "private"
                }
                self.assertIn(str(a_private_artifact.uuid), privs)
            else:
                # We don't use 'after' here so there should be no 404
                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_private_artifacts_for_user(self):
        if not Artifact.objects.exists():
            return
        artifact_don_quixote.visibility = Artifact.Visibility.PRIVATE
        artifact_don_quixote.save()

        response = self.client.get(self.list_artifact_path())

        self.assertIn(
            str(artifact_don_quixote.uuid),
            str(response.content),
            msg="Private artifact not listed for user with permission",
        )

    def test_private_artifact(self):
        if not Artifact.objects.exists():
            return
        artifact_don_quixote.visibility = Artifact.Visibility.PRIVATE
        for role in artifact_don_quixote.roles.all():
            role.delete()
        artifact_don_quixote.save()

        response = self.client.get(self.list_artifact_path())

        self.assertNotIn(
            str(artifact_don_quixote.uuid),
            str(response.content),
            msg="Private artifact listed for user without permission",
        )

    def test_public_artifacts(self):
        response = self.client.get(reverse(ListArtifact))
        as_json = response.json()

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=as_json)
        artifacts = set(a["uuid"] for a in as_json["artifacts"])

        public = [
            str(artifact.uuid)
            for artifact in Artifact.objects.filter(
                visibility=Artifact.Visibility.PUBLIC
            )
        ]

        # Ensures all public artifacts are always listed
        # DOI artifacts and private artifacts are covered by test_list_length
        for artifact in public:
            self.assertIn(
                artifact,
                artifacts,
                msg=f"Public artifact {artifact} not included in response",
            )


class TestListArtifactsEmpty(TestListArtifacts):
    @classmethod
    def setUpClass(cls):
        TestCase.setUpClass()
        Artifact.objects.all().delete()


class TestGetArtifact(TestCase, APITest):
    def test_get_artifact(self):
        artifact_don_quixote.refresh_from_db()
        response = self.client.get(self.get_artifact_path(artifact_don_quixote.uuid))
        as_json = json.loads(response.content)

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=as_json)

        self.assertAPIResponseEqual(
            as_json,
            ArtifactSerializer(artifact_don_quixote, context=self.get_test_context()),
        )

    def test_get_artifact_unauthenticated(self):
        artifact_don_quixote.refresh_from_db()
        artifact_don_quixote.visibility = Artifact.Visibility.PUBLIC
        artifact_don_quixote.save()
        response = self.client.get(
            reverse(GetArtifact, args=[artifact_don_quixote.uuid])
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.json())

    def test_get_private_artifact(self):
        artifact_don_quixote.refresh_from_db()
        artifact_don_quixote.visibility = Artifact.Visibility.PRIVATE
        for role in artifact_don_quixote.roles.all():
            role.delete()
        artifact_don_quixote.save()

        response = self.client.get(self.get_artifact_path(artifact_don_quixote.uuid))
        as_json = response.json()

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, msg=as_json)

    def test_get_private_artifact_for_user(self):
        artifact_don_quixote.refresh_from_db()
        artifact_don_quixote.visibility = Artifact.Visibility.PRIVATE
        artifact_don_quixote.save()

        response = self.client.get(self.get_artifact_path(artifact_don_quixote.uuid))
        as_json = response.json()

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=as_json)
        self.assertAPIResponseEqual(
            as_json,
            ArtifactSerializer(artifact_don_quixote, context=self.get_test_context()),
        )

    def test_get_missing_artifact(self):
        fake_uuid = uuid.uuid4()
        while True:
            try:
                Artifact.objects.get(uuid=fake_uuid)
                fake_uuid = uuid.uuid4()
            except Artifact.DoesNotExist:
                break
        response = self.client.get(self.get_artifact_path(str(fake_uuid)))
        self.assertEqual(
            response.status_code, status.HTTP_404_NOT_FOUND, msg=response.content
        )

    def test_get_private_artifact_with_sharing_key(self):
        artifact_don_quixote.refresh_from_db()
        artifact_don_quixote.visibility = Artifact.Visibility.PRIVATE
        for role in artifact_don_quixote.roles.all():
            role.delete()
        artifact_don_quixote.save()

        response = self.client.get(
            f"{self.get_artifact_path(artifact_don_quixote.uuid)}"
            f"&sharing_key={artifact_don_quixote.sharing_key}"
        )
        as_json = response.json()

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=as_json)
        self.assertAPIResponseEqual(
            as_json,
            ArtifactSerializer(artifact_don_quixote, context=self.get_test_context()),
        )

    def test_sharing_key_in_response(self):
        artifact_don_quixote.refresh_from_db()
        for role in artifact_don_quixote.roles.all():
            role.delete()
        response = self.client.get(self.get_artifact_path(artifact_don_quixote.uuid))
        as_json = response.json()
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=as_json)
        self.assertNotIn("sharing_key", as_json)

        test_token = JWT.from_jws(self.get_test_token())
        artifact_don_quixote.roles.create(
            user=test_token.to_urn(),
            assigned_by=test_token.to_urn(),
            role=ArtifactRole.RoleType.COLLABORATOR,
        )

        response = self.client.get(self.get_artifact_path(artifact_don_quixote.uuid))
        as_json = response.json()
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=as_json)
        self.assertIn("sharing_key", as_json)


class TestCreateArtifact(TestCase, APITest):
    allowed_tag1 = "!!CreateArtifactTag1!!"
    allowed_tag2 = "!!CreateArtifactTag2!!"

    @classmethod
    def setUpClass(cls):
        super(TestCreateArtifact, cls).setUpClass()
        ArtifactTag.objects.create(tag=cls.allowed_tag1)
        ArtifactTag.objects.create(tag=cls.allowed_tag2)

    def get_new_artifact(self):
        return {
            "title": "Testing CreateObject",
            "short_description": "Testing out the CreateArtifact API Endpoint.",
            "long_description": "Well, it sure is a fine day out here to create "
            "some unit tests for the Trovi CreateArtifact API endpoint. "
            "Yes siree, this sure is a mighty fine endpoint, "
            "if I do say so myself.",
            "tags": [ArtifactTag.objects.first().tag, ArtifactTag.objects.last().tag],
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
            # "linked_projects": [  TODO eventually, users will be allowed to set this
            #     "urn:trovi:chameleon:CH-1111",
            #     "urn:trovi:chameleon:CH-2222",
            # ],
            "reproducibility": {"enable_requests": True, "access_hours": 3},
            "version": {
                "contents": {
                    "urn": "urn:trovi:contents:chameleon:"
                    "108beeac-564f-4030-b126-ec4d903e680e"
                },
                "links": [
                    {
                        "label": "Training data",
                        "urn": "urn:globus:dataset:"
                        "979a1221-8c42-41bf-bb08-4a16ed981447:"
                        "/training_set",
                    },
                    {
                        "label": "Our training image",
                        "urn": "urn:trovi:chameleon:disk-image:CHI@TACC:"
                        "fd13fbc0-2d53-4084-b348-3dbd60cdc5e1",
                    },
                ],
            },
        }

    def test_create_artifact_all_params(self):
        new_artifact = self.get_new_artifact()
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
        model = Artifact.objects.get(uuid=response_body["uuid"])
        new_artifact["versions"] = [new_artifact.pop("version")]
        self.assertAPIResponseEqual(
            new_artifact, ArtifactSerializer(model, context=self.get_test_context())
        )

    def test_create_artifact_owner_admin(self):
        new_artifact = self.get_new_artifact()
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

        model = Artifact.objects.get(uuid=response_body["uuid"])
        self.assertTrue(
            model.roles.filter(
                user=model.owner_urn, role=ArtifactRole.RoleType.ADMINISTRATOR
            ).exists(),
            "New artifact owner was not automatically set as admin!",
        )

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

    @override_settings(ARTIFACT_ALLOW_ADMIN_FORCED_WRITES=True)
    def test_force(self):
        new_artifact = self.get_new_artifact()
        new_uuid = "dbc7b853-e7b9-4897-ad01-67606dd4c499"
        created_at = timezone.datetime(
            year=2049, month=7, day=6, tzinfo=timezone.get_current_timezone()
        ).strftime(settings.DATETIME_FORMAT)
        new_artifact["uuid"] = new_uuid
        new_artifact["created_at"] = created_at

        response = self.client.post(
            self.create_artifact_path(),
            content_type="application/json",
            data=new_artifact,
        )

        # Initially calling this without the force flag should fail
        self.assertIsNotNone(response)
        as_json = response.json()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, msg=as_json)

        # Add the force flag and it should succeed
        response = self.client.post(
            self.create_artifact_path(is_admin=True) + "&force",
            content_type="application/json",
            data=new_artifact,
        )

        self.assertIsNotNone(response)
        as_json = response.json()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=as_json)

        qs = Artifact.objects.filter(uuid=new_uuid)
        self.assertTrue(qs.exists())
        self.assertEqual(qs.count(), 1)
        model = qs.first()
        new_artifact["versions"] = [new_artifact.pop("version")]
        self.assertAPIResponseEqual(
            new_artifact, ArtifactSerializer(model, context=self.get_test_context())
        )


class TestUpdateArtifact(TestCase, APITest):
    def get_patch(self) -> dict:
        return {
            "patch": [
                {
                    "op": "replace",
                    "path": "/short_description",
                    "value": "I've been patched!!!",
                },
                {
                    "op": "remove",
                    "path": "/reproducibility/enable_requests",
                },
                {
                    "op": "move",
                    "from": "/long_description",
                    "path": "/title",
                },
                {
                    "op": "add",
                    "path": "/authors/1",
                    "value": {
                        "full_name": "Petey Patch",
                        "email": "petey@patchme.io",
                        "affiliation": "The Patch People",
                    },
                },
                {
                    "op": "replace",
                    "path": "/tags",
                    "value": [
                        t.tag for t in random.choices(ArtifactTag.objects.all(), k=1)
                    ],
                },
                {
                    "op": "add",
                    "path": "/linked_projects/-",
                    "value": "urn:trovi:chameleon:CH-99999",
                },
            ]
        }

    def test_update_artifact(self, forced: bool = False):
        # Ensures that the update endpoint is functioning
        # Extensive testing is not needed here, as most of the logic is
        # handled by json-patch
        artifact_don_quixote.refresh_from_db()
        old_donq_as_json = ArtifactSerializer(
            artifact_don_quixote, context=self.get_test_context()
        ).data

        patch = self.get_patch()

        if forced:
            new_timestamp = timezone.datetime(
                year=2049, month=7, day=6, tzinfo=timezone.get_current_timezone()
            ).strftime(settings.DATETIME_FORMAT)
            patch["patch"].append(
                {"op": "replace", "path": "/created_at", "value": new_timestamp}
            )
            # Assure write fails without ?force
            response = self.client.patch(
                self.update_artifact_path(artifact_don_quixote.uuid),
                content_type="application/json",
                data=patch,
            )
            self.assertEqual(
                response.status_code, status.HTTP_400_BAD_REQUEST, msg=response.json()
            )

        response = self.client.patch(
            self.update_artifact_path(artifact_don_quixote.uuid)
            + ("&force" if forced else ""),
            content_type="application/json",
            data=patch,
        )

        # If the request is bad, sometimes a tuple is returned
        self.assertIsInstance(response, Response)
        new_donq_as_json = json.loads(response.content)
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=new_donq_as_json)
        new_donq = new_donq_as_json

        # Test that the intended fields changed
        diff_msg = f"{old_donq_as_json=} {new_donq_as_json=}"
        new_description = new_donq["short_description"]
        self.assertEqual(new_description, patch["patch"][0]["value"], msg=diff_msg)
        self.assertNotEqual(
            new_description, artifact_don_quixote.short_description, msg=diff_msg
        )

        self.assertIsNone(new_donq["long_description"], msg=diff_msg)
        self.assertEqual(new_donq["title"], artifact_don_quixote.long_description)

        new_tags = patch["patch"][4]["value"]
        self.assertListEqual(
            list(sorted(new_donq_as_json["tags"])), list(sorted(new_tags)), msg=diff_msg
        )

        new_authors = new_donq["authors"]
        target_author = patch["patch"][3]["value"]
        self.assertIn(target_author, new_authors, msg=diff_msg)
        self.assertEqual(new_authors[1], target_author, msg=diff_msg)

        new_projects = new_donq["linked_projects"]
        target_project = patch["patch"][5]["value"]
        self.assertIn(target_project, new_projects, msg=diff_msg)

        if forced:
            self.assertEqual(new_donq["created_at"], new_timestamp, msg=diff_msg)

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
        old_donq_as_json.pop("tags")
        new_donq_as_json.pop("tags")
        new_donq_as_json.pop("sharing_key", None)
        old_donq_as_json.pop("sharing_key", None)
        old_donq_as_json["authors"] = [
            a for a in old_donq_as_json["authors"] if a != target_author
        ]
        new_donq_as_json["authors"] = [
            a for a in new_donq_as_json["authors"] if a != target_author
        ]
        old_donq_as_json["linked_projects"] = [
            p
            for p in sorted(old_donq_as_json["linked_projects"])
            if p != target_project
        ]
        new_donq_as_json["linked_projects"] = [
            p
            for p in sorted(new_donq_as_json["linked_projects"])
            if p != target_project
        ]
        if forced:
            old_donq_as_json.pop("created_at")
            new_donq_as_json.pop("created_at")
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

    def test_update_artifact_no_permission(self):
        # TODO
        pass

    @override_settings(ARTIFACT_ALLOW_ADMIN_FORCED_WRITES=True)
    def test_update_artifact_force(self):
        self.test_update_artifact(forced=True)


class TestCreateArtifactVersion(TestCase, APITest):
    example_version = {
        "contents": {
            "urn": "urn:trovi:contents:chameleon:108beeac-564f-4030-b126-ec4d903e680e"
        },
        "links": [
            {
                "label": "Training data",
                "urn": "urn:globus:dataset:"
                "979a1221-8c42-41bf-bb08-4a16ed981447:"
                "/training_set",
            },
            {
                "label": "Our training image",
                "urn": "urn:trovi:chameleon:disk-image:CHI@TACC:"
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

    def test_create_artifact_version_insufficient_role(self):
        artifact_don_quixote.refresh_from_db()
        test_token = JWT.from_jws(self.get_test_token())
        artifact_don_quixote.roles.get(user=test_token.to_urn()).delete()
        response = self.client.post(
            self.create_artifact_version_path(artifact_don_quixote.uuid),
            content_type="application/json",
            data=self.example_version,
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_artifact_version(self):
        artifact_don_quixote.refresh_from_db()
        old_updated_at = artifact_don_quixote.updated_at

        response = self.client.post(
            self.create_artifact_version_path(artifact_don_quixote.uuid),
            content_type="application/json",
            data=self.example_version,
        )

        self.assertEqual(
            response.status_code, status.HTTP_201_CREATED, msg=response.content
        )
        response_body = response.json()
        artifact_don_quixote.refresh_from_db()
        new_updated_at = artifact_don_quixote.updated_at

        model = ArtifactVersion.objects.get(
            contents_urn=response_body["contents"]["urn"]
        )
        self.assertAPIResponseEqual(response_body, ArtifactVersionSerializer(model))
        self.assertEqual(artifact_don_quixote.uuid, model.artifact.uuid)
        self.assertIn(model, artifact_don_quixote.versions.all())
        self.assertGreater(
            new_updated_at,
            old_updated_at,
            msg="Creating new version did not mark parent artifact as updated.",
        )

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
        make_admin(random_artifact)
        response_2 = self.client.post(
            self.create_artifact_version_path(random_artifact.uuid),
            content_type="application/json",
            data=example,
        )

        self.assertEqual(
            response_2.status_code, status.HTTP_409_CONFLICT, msg=response_2.content
        )

    def test_create_artifact_version_slug(self):
        example_1 = copy.deepcopy(self.example_version)
        example_1["contents"]["urn"] = f"urn:trovi:contents:chameleon:{uuid.uuid4()}"
        example_2 = copy.deepcopy(self.example_version)
        example_2["contents"]["urn"] = f"urn:trovi:contents:chameleon:{uuid.uuid4()}"

        response_1 = self.client.post(
            self.create_artifact_version_path(artifact_don_quixote.uuid),
            content_type="application/json",
            data=example_1,
        )

        self.assertEqual(
            response_1.status_code, status.HTTP_201_CREATED, msg=response_1.json()
        )

        response_2 = self.client.post(
            self.create_artifact_version_path(artifact_don_quixote.uuid),
            content_type="application/json",
            data=example_2,
        )

        self.assertEqual(
            response_2.status_code, status.HTTP_201_CREATED, msg=response_2.json()
        )

        version_1 = ArtifactVersion.objects.get(
            contents_urn=example_1["contents"]["urn"]
        )

        version_2 = ArtifactVersion.objects.get(
            contents_urn=example_2["contents"]["urn"]
        )

        # Assert that versions created on the same day have an incrementing '.n' suffix
        self.assertIn(".", version_1.slug)
        self.assertIn(".", version_2.slug)
        suffix_1 = version_1.slug.split(".")[-1]
        suffix_2 = version_2.slug.split(".")[-1]
        self.assertEqual(
            int(suffix_2),
            int(suffix_1) + 1,
            msg="Versions from the same day do not properly increment suffixes",
        )

    def test_create_artifact_version_no_write_scope(self):
        # TODO
        pass


class TestDeleteArtifactVersion(TestCase, APITest):
    def test_endpoint_works(self):
        try:
            base_response = self.client.delete(
                self.delete_artifact_version_path(str(artifact_don_quixote.uuid), "foo")
            )
            self.assertIsNotNone(base_response)
        except Exception as e:
            self.fail(e)

    def test_delete_artifact_version(self):
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
        request_url = self.authenticate_url(
            reverse(
                DeleteArtifactVersion,
                args=[
                    artifact_don_quixote.uuid,
                    version_don_quixote_1.slug,
                ],
            ),
            scopes=[JWT.Scopes.ARTIFACTS_READ],
        )
        response = self.client.delete(request_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
            "Deleted artifact version with insufficient scope",
        )

    def test_delete_artifact_version_not_collaborator(self):
        for role in artifact_don_quixote.roles.all():
            role.delete()

        response = self.client.delete(
            self.delete_artifact_version_path(
                str(artifact_don_quixote.uuid), version_don_quixote_1.slug
            )
        )
        self.assertIsNotNone(response)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
            msg="Deleted artifact version with insufficient role",
        )

    def test_delete_artifact_version_has_doi(self):
        version_don_quixote_1.contents_urn = "urn:trovi:contents:zenodo:foobar"
        version_don_quixote_1.save()
        response = self.client.delete(
            self.delete_artifact_version_path(
                str(artifact_don_quixote.uuid), version_don_quixote_1.slug
            )
        )
        self.assertIsNotNone(response)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
            msg="Deleted artifact version with DOI",
        )


class TestIncrArtifactVersionMetrics(TestCase, APITest):
    def test_endpoint_works(self):
        try:
            base_response = self.client.put(
                self.incr_artifact_version_metrics_path(
                    str(artifact_don_quixote.uuid), "foo", "access_count"
                )
            )
            self.assertIsNotNone(base_response)
        except Exception as e:
            self.fail(e)

    def do_access_count_test(self, amount: int = None):
        version_don_quixote_1.refresh_from_db()
        artifact_don_quixote.refresh_from_db()
        target_version_access_count = version_don_quixote_1.access_count + (amount or 1)
        target_artifact_access_count = artifact_don_quixote.access_count + (amount or 1)
        base_response = self.client.put(
            self.incr_artifact_version_metrics_path(
                str(artifact_don_quixote.uuid),
                version_don_quixote_1.slug,
                "access_count",
                amount=amount,
            )
        )

        self.assertEqual(base_response.status_code, status.HTTP_204_NO_CONTENT)

        version_don_quixote_1.refresh_from_db()
        artifact_don_quixote.refresh_from_db()
        self.assertEqual(
            target_version_access_count,
            version_don_quixote_1.access_count,
            msg=f"{amount=}",
        )
        self.assertEqual(
            target_artifact_access_count,
            artifact_don_quixote.access_count,
            msg=f"{amount=}",
        )

    def do_unique_access_count_test(self, amount: int = None):
        version_don_quixote_1.refresh_from_db()
        artifact_don_quixote.refresh_from_db()
        target_version_unique_access_count = version_don_quixote_1.unique_access_count
        base_response = self.client.put(
            self.incr_artifact_version_metrics_path(
                str(artifact_don_quixote.uuid),
                version_don_quixote_1.slug,
                "access_count",
                amount=amount,
            )
        )

        self.assertEqual(base_response.status_code, status.HTTP_204_NO_CONTENT)

        version_don_quixote_1.refresh_from_db()
        self.assertEqual(
            target_version_unique_access_count,
            version_don_quixote_1.unique_access_count,
            msg=f"{amount=}",
        )

    def do_unique_cell_execution_count_test(self, amount: int = None):
        version_don_quixote_1.refresh_from_db()
        artifact_don_quixote.refresh_from_db()
        target_version_cell_execution_count = (
            version_don_quixote_1.unique_cell_execution_count + (amount or 1)
        )
        base_response = self.client.put(
            self.incr_artifact_version_metrics_path(
                str(artifact_don_quixote.uuid),
                version_don_quixote_1.slug,
                "cell_execution_count",
                amount=amount,
            )
        )

        self.assertEqual(base_response.status_code, status.HTTP_204_NO_CONTENT)

        version_don_quixote_1.refresh_from_db()
        self.assertEqual(
            target_version_cell_execution_count,
            version_don_quixote_1.unique_cell_execution_count,
            msg=f"{amount=}",
        )

    def test_increment_access_count(self):
        self.do_access_count_test()
        self.do_access_count_test(amount=5)
        self.do_unique_access_count_test()

    def test_increment_cell_execution_count(self):
        self.do_unique_cell_execution_count_test()
        self.do_access_count_test(amount=5)

    def test_increment_metrics_no_scope(self):
        metrics_path_no_scope = self.authenticate_url(
            f"{reverse(IncrArtifactVersionMetrics, args=[artifact_don_quixote.uuid, version_don_quixote_1.slug])}"
            f"?metric=cell_execution_count&origin={self.get_test_token()}&amount=1",
            scopes=[JWT.Scopes.ARTIFACTS_WRITE],
        )
        base_response = self.client.put(metrics_path_no_scope)

        self.assertEqual(
            base_response.status_code,
            status.HTTP_403_FORBIDDEN,
            msg=base_response.content,
        )

    def test_increment_metrics_private(self):
        artifact_don_quixote.refresh_from_db()
        artifact_don_quixote.visibility = Artifact.Visibility.PRIVATE
        for role in artifact_don_quixote.roles.all():
            role.delete()
        artifact_don_quixote.save()

        response = self.client.put(
            self.incr_artifact_version_metrics_path(
                artifact_don_quixote.uuid,
                version_don_quixote_1.slug,
                "cell_execution_count",
                amount=1,
            )
        )

        self.assertEqual(
            response.status_code, status.HTTP_403_FORBIDDEN, msg=response.content
        )


class TestAssignArtifactRole(TestCase, APITest):
    test_user = "urn:trovi:user:chameleon:foobar@baz.biz"

    def test_endpoint_works(self):
        try:
            base_response = self.client.post(
                self.assign_artifact_role_path(artifact_don_quixote.uuid)
            )
            self.assertIsNotNone(base_response)
        except Exception as e:
            self.fail(e)

    def test_assign_role(self):
        artifact_don_quixote.refresh_from_db()
        response = self.client.post(
            self.assign_artifact_role_path(artifact_don_quixote.uuid),
            content_type="application/json",
            data={"user": self.test_user, "role": ArtifactRole.RoleType.COLLABORATOR},
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        new_role_query = artifact_don_quixote.roles.filter(
            user=self.test_user, role=ArtifactRole.RoleType.COLLABORATOR
        )

        self.assertEqual(new_role_query.count(), 1)

    def test_assign_role_non_admin(self):
        artifact_don_quixote.refresh_from_db()
        for role in artifact_don_quixote.roles.all():
            role.delete()
        response = self.client.post(
            self.assign_artifact_role_path(artifact_don_quixote.uuid),
            content_type="application/json",
            data={"user": self.test_user, "role": ArtifactRole.RoleType.COLLABORATOR},
        )
        self.assertEqual(
            response.status_code, status.HTTP_403_FORBIDDEN, response.content
        )

        test_token = JWT.from_jws(self.get_test_token())
        artifact_don_quixote.roles.create(
            user=test_token.to_urn(),
            role=ArtifactRole.RoleType.COLLABORATOR,
            assigned_by=artifact_don_quixote.owner_urn,
        )
        response = self.client.post(
            self.assign_artifact_role_path(artifact_don_quixote.uuid),
            content_type="application/json",
            data={"user": self.test_user, "role": ArtifactRole.RoleType.COLLABORATOR},
        )
        self.assertEqual(
            response.status_code, status.HTTP_403_FORBIDDEN, response.content
        )

    def assign_role_conflict(self):
        test_role = artifact_don_quixote.roles.first()
        response = self.client.post(
            self.assign_artifact_role_path(artifact_don_quixote.uuid),
            content_type="application/json",
            data={"user": test_role.user, "role": test_role.role},
        )

        self.assertEqual(
            response.status_code, status.HTTP_409_CONFLICT, "Created duplicate role"
        )


class TestUnassignArtifactRole(TestCase, APITest):
    def test_endpoint_works(self):
        try:
            base_response = self.client.delete(
                self.unassign_artifact_role_path(
                    artifact_don_quixote.uuid, "foo", ArtifactRole.RoleType.COLLABORATOR
                )
            )
            self.assertIsNotNone(base_response)
        except Exception as e:
            self.fail(e)

    def test_unassign_role(self):
        response = self.client.delete(
            self.unassign_artifact_role_path(
                artifact_don_quixote.uuid,
                role_don_quixote_admin.user,
                role_don_quixote_admin.role,
            )
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        self.assertFalse(
            artifact_don_quixote.roles.filter(
                user=role_don_quixote_admin.user, role=role_don_quixote_admin.role
            ).exists(),
            "UnassignRole did not delete target role",
        )

    def test_unassign_role_non_admin(self):
        artifact_don_quixote.refresh_from_db()
        for role in artifact_don_quixote.roles.all():
            role.delete()
        test_user = "urn:trovi:user:chameleon:foo@bar.baz"
        artifact_don_quixote.roles.create(
            user=test_user,
            role=ArtifactRole.RoleType.COLLABORATOR,
            assigned_by=test_user,
        )

        response = self.client.delete(
            self.unassign_artifact_role_path(
                artifact_don_quixote.uuid, test_user, ArtifactRole.RoleType.COLLABORATOR
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
            "Unassigned role without admin access",
        )

    def test_unassign_owner_as_admin(self):
        response = self.client.delete(
            self.unassign_artifact_role_path(
                artifact_don_quixote.uuid,
                role_don_quixote_don.user,
                role_don_quixote_don.role,
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
            "Unassigned admin role from owner",
        )

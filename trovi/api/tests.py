import datetime
import json
import random
from typing import Optional, Union, Iterable

import faker.config
from django.conf import settings
from django.db import transaction, IntegrityError, models
from django.http import JsonResponse
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from trovi.api.serializers import ArtifactSerializer
from trovi.api.urls import ListArtifact, GetArtifact, CreateArtifact, UpdateArtifact
from trovi.models import (
    Artifact,
    ArtifactVersion,
    ArtifactTag,
    ArtifactAuthor,
    ArtifactProject,
    ArtifactEvent,
    ArtifactLink,
)
from util.test import DummyArtifact


def cut_string(s: str, max_length: int) -> str:
    return s[: min(len(s), max_length)]


fake = faker.Faker(faker.config.AVAILABLE_LOCALES)

CHI_SITES = ["TACC", "UC", "NU"]


def fake_email() -> str:
    return cut_string(
        random.choice(
            [
                fake.email,
                fake.free_email,
                fake.safe_email,
                fake.ascii_email,
                fake.company_email,
                fake.ascii_company_email,
                fake.ascii_free_email,
                fake.ascii_safe_email,
            ]
        )(),
        settings.EMAIL_ADDRESS_MAX_CHARS,
    )


def fake_github_user() -> str:
    """Generates a fake, valid GitHub name"""
    return cut_string(fake.user_name(), settings.GITHUB_USERNAME_MAX_CHARS)


def fake_github_repo() -> str:
    return cut_string(
        random.choice(
            [
                fake.domain_name,
                fake.user_name,
                fake.random_object_name,
                fake.slug,
            ]
        )(),
        settings.GITHUB_REPO_NAME_MAX_CHARS,
    )


def fake_git_ref() -> str:
    if not fake.boolean(chance_of_getting_true=80):
        return ""
    else:
        use_commit_id = fake.boolean(chance_of_getting_true=40)
        git_hash = fake.sha1()
        return (
            "@"
            + random.choice(
                [
                    lambda: cut_string(fake.slug(), settings.GIT_BRANCH_NAME_MAX_CHARS),
                    lambda: git_hash[: 7 if use_commit_id else len(git_hash)],
                ]
            )()
        )


def fake_contents_urn() -> str:
    return (
        "urn:"
        + random.choice(
            [
                lambda: f"chameleon:{fake.uuid4()}",
                lambda: f"zenodo:{fake.doi()}",
                lambda: f"github:{fake_github_user()}/{fake_github_repo()}"
                f"{fake_git_ref()}",
            ]
        )()
    )


def fake_user_urn() -> str:
    return f"urn:chameleon:{fake_email()}"


def fake_project_urn() -> str:
    return f"urn:chameleon:CHI-{fake.unique.random_int(1, 999999)}"


def fake_link_urn() -> str:
    return (
        "urn:"
        + random.choice(
            [
                lambda: f"disk-image:CHI@{random.choice(CHI_SITES)}:{fake.uuid4()}",
                # TODO unsure of how fabric data should be formatted
                # lambda: f"disk-image:fabric:{fake.slug()}:{fake.uuid4()}",
                lambda: f"dataset:globus:{fake.uuid4()}:{fake.uri_path()}",
                lambda: f"dataset:CHI@{random.choice(CHI_SITES)}:{fake.uuid4()}:"
                f"{fake.uri_path()}",
                lambda: f"dataset:zenodo:{fake.doi()}:{fake.uri_path()}",
            ]
        )()
    )


def fake_tag() -> str:
    return cut_string(
        random.choice(
            [
                fake.domain_word,
                fake.department_name,
                fake.company,
                fake.name,
                fake.domain_name,
                lambda: str(fake.random_int()),
            ]
        )(),
        settings.ARTIFACT_TAG_MAX_CHARS,
    )


# Sample Artifacts which define expected input
# Tests against an artifact with multiple versions on the same backend, multiple tags,
# multiple authors, multiple events of the same type, and multiple links
artifact_don_quixote = Artifact(
    uuid="fee870d8-5021-4de3-be45-2eca747285c6",
    title="Evaluating Windmill-Based Threat Models",
    short_description="Are they, or aren't they, actually giants?",
    long_description="foo",
    owner_urn="urn:chameleon:donquixote",
    visibility=Artifact.Visibility.PUBLIC,
    is_reproducible=True,
    repro_access_hours=3,
)
version_don_quixote_1 = ArtifactVersion(
    artifact=artifact_don_quixote,
    contents_urn="urn:swift:donquixote1",
)
version_don_quixote_2 = ArtifactVersion(
    artifact=artifact_don_quixote,
    contents_urn="urn:swift:donquixote2",
)
author_don_quixote_don = ArtifactAuthor(
    artifact=artifact_don_quixote,
    full_name="El ingenioso hidalgo don Quixote de la Mancha",
    affiliation="The Duchess",
    email="donq@rocinante.io",
)
author_don_quixote_sancho = ArtifactAuthor(
    artifact=artifact_don_quixote,
    full_name="Sancho Panza",
    affiliation="The Duchess",
    email="sancho@rocinante.io",
)
event_don_quixote_launch1 = ArtifactEvent(
    artifact_version=version_don_quixote_1,
    event_type=ArtifactEvent.EventType.LAUNCH,
    event_origin="urn:chameleon:dulcinea@toboso.gov",
)
event_don_quixote_launch2 = ArtifactEvent(
    artifact_version=version_don_quixote_2,
    event_type=ArtifactEvent.EventType.LAUNCH,
    event_origin="urn:chameleon:dulcinea@toboso.gov",
)
event_don_quixote_launch3 = ArtifactEvent(
    artifact_version=version_don_quixote_2,
    event_type=ArtifactEvent.EventType.LAUNCH,
    event_origin="urn:chameleon:dulcinea@toboso.gov",
)
link_don_quixote_dataset = ArtifactLink(
    artifact_version=version_don_quixote_1,
    urn="urn:dataset:globus:9a7c09d3-80e7-466c-9325-423f4358db96:/data",
    label="Windmill Data",
)
link_don_quixote_image = ArtifactLink(
    artifact_version=version_don_quixote_2,
    urn="urn:disk-image:chameleon:CHI@UC:fbcf21f7-8397-43d1-a9ef-55c3eee868f7",
    label="Image of DuchessOS",
)
don_quixote = [
    artifact_don_quixote,
    version_don_quixote_1,
    version_don_quixote_2,
    author_don_quixote_sancho,
    author_don_quixote_don,
    event_don_quixote_launch1,
    event_don_quixote_launch2,
    event_don_quixote_launch3,
    link_don_quixote_image,
    link_don_quixote_dataset,
]


def generate_fake_artifact() -> list[models.Model]:
    """Generates a fake artifact with a random series of attributes"""
    artifact = Artifact(
        uuid=fake.uuid4(),
        title=fake.text(max_nb_chars=settings.ARTIFACT_TITLE_MAX_CHARS),
        short_description=fake.text(
            max_nb_chars=settings.ARTIFACT_SHORT_DESCRIPTION_MAX_CHARS
        ),
        long_description=fake.text(
            max_nb_chars=settings.ARTIFACT_LONG_DESCRIPTION_MAX_CHARS
        ),
        owner_urn=fake_user_urn(),
        visibility=random.choice(Artifact.Visibility.values),
    )
    artifact_versions = [
        ArtifactVersion(
            artifact=artifact,
            contents_urn=fake_contents_urn(),
        )
        for _ in range(0, random.randint(1, 20))
    ]
    artifact_authors = [
        ArtifactAuthor(
            artifact=artifact,
            full_name=cut_string(fake.name(), settings.ARTIFACT_AUTHOR_NAME_MAX_CHARS),
            affiliation=cut_string(
                random.choice([fake.company, fake.building_name])(),
                settings.ARTIFACT_AUTHOR_AFFILIATION_MAX_CHARS,
            ),
            email=fake_email(),
        )
        for _ in range(0, random.randint(1, 10))
    ]
    artifact_events = [
        ArtifactEvent(
            artifact_version=random.choice(artifact_versions),
            event_type=random.choice(ArtifactEvent.EventType.values),
            event_origin=None
            if fake.boolean(chance_of_getting_true=90)
            else fake_user_urn(),
        )
        for _ in range(random.randint(0, 400))
    ]

    def _verified() -> dict[str, Union[bool, Optional[datetime.datetime]]]:
        # Generates random but correct verification attributes for a link
        verified = fake.boolean(chance_of_getting_true=20)
        return {
            "verified": verified,
            "verified_at": None
            if not verified
            else fake.date_time_between(
                datetime.date.min, datetime.date.max, timezone.utc
            ),
        }

    artifact_links = [
        ArtifactLink(
            artifact_version=random.choice(artifact_versions),
            urn=fake_link_urn(),
            label=fake.text(max_nb_chars=settings.ARTIFACT_LINK_LABEL_MAX_CHARS),
            **_verified(),
        )
        for _ in range(random.randint(0, 3))
    ]

    # The value returned is a single flat list of all the models just created
    return [artifact] + sum(
        [
            artifact_versions,
            artifact_authors,
            artifact_events,
            artifact_links,
        ],
        start=[],
    )


def generate_many_to_many(artifacts: Iterable[Artifact]):
    """
    Generates random many-to-many attributes and applies them to artifacts.
    This function should only be called after the test artifacts
    have already been saved.
    """
    tags = [
        ArtifactTag.objects.create(
            tag=fake.text(max_nb_chars=settings.ARTIFACT_TAG_MAX_CHARS)
        )
        for _ in range(random.randint(0, 100))
    ]

    projects = [
        ArtifactProject.objects.create(urn=fake_project_urn())
        for _ in range(random.randint(1, 1000))
    ]

    # Randomly weigh the attributes to simulate some being more popular than others
    weights_tags = [random.random() for _ in tags]
    weights_projects = [random.random() for _ in projects]

    for artifact in artifacts:
        k_tags = random.randint(0, len(tags))
        if k_tags:
            # Apply the tags randomly to artifacts
            artifact.tags.add(*random.choices(tags, weights=weights_tags, k=k_tags))
        k_projects = random.randint(1, len(projects))
        # Apply the projects randomly to artifacts
        artifact.linked_projects.add(
            *random.choices(projects, weights=weights_projects, k=k_projects)
        )


class APITestCase(TransactionTestCase):
    renderer = JSONRenderer()
    maxDiff = None

    @staticmethod
    def list_artifact_path():
        return reverse(ListArtifact)

    @staticmethod
    def get_artifact_path(uuid: str):
        return reverse(GetArtifact, args=[uuid])

    @staticmethod
    def create_artifact_path():
        return reverse(CreateArtifact)

    @staticmethod
    def update_artifact_path(uuid: str):
        return reverse(UpdateArtifact, args=[uuid])

    @classmethod
    def setUpClass(cls):
        print("Generating test data...")
        super(APITestCase, cls).setUpClass()
        all_models = don_quixote + sum(
            [generate_fake_artifact() for _ in range(100)], start=[]
        )
        try:
            with transaction.atomic():
                for model in all_models:
                    model.save()
            with transaction.atomic():
                generate_many_to_many(Artifact.objects.all())
        except IntegrityError as e:
            assert False, str(e)
        print("Finished.")

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
        TransactionTestCase.setUpClass()


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

"""
Helper data classes used for dot-referencing API responses
Not meant to be robust, and mostly unvalidated, but helpful to avoid
having to reference dicts with strings repeatedly in tests.
"""

import datetime
import logging
import os
import random
from typing import Union, Optional, Iterable, Any
from uuid import uuid4

import faker.config
from django.conf import settings
from django.db import models, transaction, IntegrityError
from django.test.runner import DiscoverRunner
from django.utils import timezone

from trovi.models import (
    Artifact,
    ArtifactVersion,
    ArtifactAuthor,
    ArtifactEvent,
    ArtifactLink,
    ArtifactTag,
    ArtifactProject,
    ArtifactRole,
)


def cut_string(s: str, max_length: int) -> str:
    return s[: min(len(s), max_length)]


logging.getLogger("faker.factory").setLevel(logging.INFO)
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
        "urn:trovi:contents:"
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
    return f"urn:trovi:user:chameleon:{fake_email()}"


def fake_project_urn() -> str:
    return f"urn:trovi:chameleon:CHI-{fake.unique.random_int(1, 999999)}"


def fake_link_urn() -> str:
    return (
        "urn:"
        + random.choice(
            [
                lambda: f"trovi:chameleon:disk-image:CHI@{random.choice(CHI_SITES)}:{fake.uuid4()}",
                # TODO unsure of how fabric data should be formatted
                # lambda: f"disk-image:fabric:{fake.slug()}:{fake.uuid4()}",
                lambda: f"globus:dataset:{fake.uuid4()}:{fake.uri_path()}",
                lambda: f"trovi:chameleon:dataset:CHI@{random.choice(CHI_SITES)}:{fake.uuid4()}:"
                f"{fake.uri_path()}",
                lambda: f"trovi:dataset:zenodo:{fake.doi()}:{fake.uri_path()}",
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
    owner_urn="urn:trovi:user:chameleon:donquixote@rosinante.io",
    visibility=Artifact.Visibility.PUBLIC,
    is_reproducible=True,
    repro_access_hours=3,
)
artifact_don_quixote.created_at -= datetime.timedelta(days=2)

version_don_quixote_1 = ArtifactVersion(
    artifact=artifact_don_quixote,
    contents_urn=f"urn:trovi:contents:chameleon:{uuid4()}",
)
version_don_quixote_2 = ArtifactVersion(
    artifact=artifact_don_quixote,
    contents_urn=f"urn:trovi:contents:chameleon:{uuid4()}",
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
    event_origin="urn:trovi:user:chameleon:dulcinea@toboso.gov",
)
event_don_quixote_launch2 = ArtifactEvent(
    artifact_version=version_don_quixote_2,
    event_type=ArtifactEvent.EventType.LAUNCH,
    event_origin="urn:trovi:user:chameleon:dulcinea@toboso.gov",
)
event_don_quixote_launch3 = ArtifactEvent(
    artifact_version=version_don_quixote_2,
    event_type=ArtifactEvent.EventType.LAUNCH,
    event_origin="urn:trovi:user:chameleon:dulcinea@toboso.gov",
)
link_don_quixote_dataset = ArtifactLink(
    artifact_version=version_don_quixote_1,
    urn="urn:globus:dataset:9a7c09d3-80e7-466c-9325-423f4358db96:/data",
    label="Windmill Data",
)
link_don_quixote_image = ArtifactLink(
    artifact_version=version_don_quixote_2,
    urn="urn:trovi:chameleon:disk-image:CHI@UC:fbcf21f7-8397-43d1-a9ef-55c3eee868f7",
    label="Image of DuchessOS",
)
role_don_quixote_admin = ArtifactRole(
    artifact=artifact_don_quixote,
    user=f"urn:trovi:user:chameleon:{os.getenv('CHAMELEON_KEYCLOAK_TEST_USER_USERNAME')}",
    assigned_by="urn:trovi:user:chameleon:donq@rosinante.io",
    role=ArtifactRole.RoleType.ADMINISTRATOR,
)
role_don_quixote_don = ArtifactRole(
    artifact=artifact_don_quixote,
    user=artifact_don_quixote.owner_urn,
    assigned_by=artifact_don_quixote.owner_urn,
    role=ArtifactRole.RoleType.ADMINISTRATOR,
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
    role_don_quixote_admin,
    role_don_quixote_don,
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
        for _ in range(0, random.randint(1, 10))
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
            event_origin=(
                None if fake.boolean(chance_of_getting_true=90) else fake_user_urn()
            ),
        )
        for _ in range(random.randint(0, 40))
    ]

    def _verified() -> dict[str, Union[bool, Optional[datetime.datetime]]]:
        # Generates random but correct verification attributes for a link
        verified = fake.boolean(chance_of_getting_true=20)
        return {
            "verified": verified,
            "verified_at": (
                None
                if not verified
                else fake.date_time_between(
                    datetime.date.min, datetime.date.max, timezone.utc
                )
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
        for _ in range(random.randint(5, 20))
    ]

    projects = [
        ArtifactProject.objects.create(urn=fake_project_urn())
        for _ in range(random.randint(1, 10))
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


def make_admin(artifact: Artifact) -> Artifact:
    artifact.roles.create(
        artifact=artifact,
        user=role_don_quixote_admin.user,
        assigned_by=role_don_quixote_admin.assigned_by,
        role=ArtifactRole.RoleType.ADMINISTRATOR,
    )
    return artifact


class SampleDataTestRunner(DiscoverRunner):
    def setup_databases(self, **kwargs) -> list[Any]:
        names = super(SampleDataTestRunner, self).setup_databases(**kwargs)
        print("Generating test data...")
        all_models = sum([generate_fake_artifact() for _ in range(100)], start=[])
        try:
            with transaction.atomic():
                for model in don_quixote:
                    model.save()
                for model in all_models:
                    model.save()
                generate_many_to_many(
                    Artifact.objects.exclude(uuid=artifact_don_quixote.uuid)
                )
        except IntegrityError as e:
            assert False, str(e)
        print("Finished.")
        return names

    def teardown_databases(self, old_config, **kwargs):
        super(SampleDataTestRunner, self).teardown_databases(old_config, **kwargs)

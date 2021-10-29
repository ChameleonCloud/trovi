import json
from django.test import TestCase

from trovi.models import (
    Artifact,
    ArtifactVersion,
    ArtifactTag,
    ArtifactAuthor,
    ArtifactProject,
    ArtifactEvent,
    ArtifactLink,
)


class TestListArtifact(TestCase):
    def setUp(self):
        test_artifact = Artifact.objects.create(
            title="Test Artifact",
            short_description="Test Short Description",
            long_description="Test Long Description",
            owner_urn="urn:trovi:1234",
        )

        test_version = ArtifactVersion.objects.create(
            slug="test_artifact", artifact=test_artifact, contents_urn="urn:trovi:4567"
        )

        ArtifactTag.objects.create(artifact=test_artifact, tag="test tag")

        ArtifactAuthor.objects.create(
            artifact=test_artifact,
            full_name="Don Quixote",
            affiliation="The Duchess",
            email="donq@rosinante.io",
        )

        ArtifactProject.objects.create(artifact=test_artifact, urn="urn:trovi:0000")

        ArtifactEvent.objects.create(
            artifact_version=test_version, event_type=ArtifactEvent.EventType.LAUNCH
        )

        ArtifactLink.objects.create(artifact_version=test_version, urn="urn:trovi:beef")

        print(json.dumps(Artifact.objects.get(uuid=test_artifact.uuid).to_json()))

    def test_list_artifact(self):
        self.assertEqual(0, 0)

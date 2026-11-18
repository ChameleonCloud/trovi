import base64
import json
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from github import UnknownObjectException
from rest_framework import exceptions as drf_exceptions, status

from trovi.api.serializers import (
    ArtifactPublicationSerializer,
    ArtifactVersionSetupSerializer,
    ArtifactVideoSerializer,
)
from trovi.importing.export import artifact_crate
from trovi.importing.views import ArtifactImportView
from trovi.models import (
    Artifact,
    ArtifactAuthor,
    ArtifactPublication,
    ArtifactTag,
    ArtifactVersion,
    ArtifactVersionSetup,
    ArtifactVideo,
)
from util.types import DummyRequest

REPO = "https://github.com/chameleoncloud/trovi"


def build_crate(root_properties: dict, extra_entities: list = None) -> dict:
    """
    Builds a minimal RO-Crate document.

    The view writes it to disk and reads it back, so these tests exercise the
    same dereferencing an import relies on.
    """
    graph = [
        {
            "@id": "trovi.json",
            "@type": "CreativeWork",
            "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            "about": {"@id": "./"},
        },
        {
            "@id": "./",
            "@type": "Dataset",
            # The importer reads these unconditionally
            "name": "Test Artifact",
            "keywords": "one, two",
            "author": [{"@id": "#alice"}],
            **root_properties,
        },
        {"@id": "#alice", "@type": "Person", "name": "Alice", "email": "a@b.co"},
    ]
    # rocrate requires a @type on every contextual entity; the tests only
    # care about the properties, so supply a default where one is omitted
    for entity in extra_entities or []:
        graph.append({"@type": "Thing", **entity})
    return {"@context": "https://w3id.org/ro/crate/1.1/context", "@graph": graph}


def stub_github(crate_json: dict = None, files: dict = None) -> mock.MagicMock:
    """
    Returns a stand-in for the GitHub client, for a repository holding crate_json
    as its trovi.json, if given, and files, by path.
    """
    files = (files or {}) | (
        {settings.RO_CRATE_FILENAME: json.dumps(crate_json)} if crate_json else {}
    )

    def get_contents(path, ref):
        if path not in files:
            raise UnknownObjectException(404)
        return mock.Mock(content=base64.b64encode(files[path].encode()))

    repo = mock.Mock(html_url=REPO)
    repo.get_commits.return_value = [mock.Mock(sha="0" * 40)]
    repo.get_contents.side_effect = get_contents
    client = mock.MagicMock()
    client.__enter__.return_value.get_repo.return_value = repo
    return client


def import_crate(crate_json: dict, files: dict = None) -> dict:
    """Runs the import against a crate, with GitHub stubbed out."""
    with mock.patch(
        "trovi.importing.views.Github", return_value=stub_github(crate_json, files)
    ):
        return ArtifactImportView()._parse_git_url(REPO, None)


class TestImportVideos(SimpleTestCase):
    def parse(self, root_properties, extra_entities=None):
        return import_crate(build_crate(root_properties, extra_entities))["videos"]

    def test_no_video_property(self):
        self.assertListEqual(self.parse({"name": "x"}), [])

    def test_external_entity_id_is_the_url(self):
        # The RO-Crate convention for an entity hosted outside the crate
        self.assertListEqual(
            self.parse(
                {"video": [{"@id": "https://youtu.be/abc"}]},
                [{"@id": "https://youtu.be/abc", "@type": "VideoObject"}],
            ),
            [{"url": "https://youtu.be/abc"}],
        )

    def test_entity_with_url_property(self):
        self.assertListEqual(
            self.parse(
                {"video": [{"@id": "#v"}]},
                [
                    {
                        "@id": "#v",
                        "@type": "VideoObject",
                        "url": "https://vimeo.com/42",
                    }
                ],
            ),
            [{"url": "https://vimeo.com/42"}],
        )

    def test_multiple_preserve_order(self):
        self.assertListEqual(
            self.parse(
                {
                    "video": [
                        {"@id": "https://youtu.be/one"},
                        {"@id": "https://youtu.be/two"},
                    ]
                },
                [
                    {"@id": "https://youtu.be/one", "@type": "VideoObject"},
                    {"@id": "https://youtu.be/two", "@type": "VideoObject"},
                ],
            ),
            [{"url": "https://youtu.be/one"}, {"url": "https://youtu.be/two"}],
        )


class TestImportPublications(SimpleTestCase):
    def parse(self, root_properties, extra_entities=None):
        return import_crate(build_crate(root_properties, extra_entities))[
            "publications"
        ]

    def test_no_citation_property(self):
        self.assertListEqual(self.parse({"name": "x"}), [])

    def test_singular_citation(self):
        # The form the RO-Crate spec's own example uses
        data = self.parse(
            {"citation": {"@id": "https://doi.org/10.1145/1.2"}},
            [
                {
                    "@id": "https://doi.org/10.1145/1.2",
                    "@type": "ScholarlyArticle",
                    "name": "A Paper",
                }
            ],
        )
        self.assertEqual([p["title"] for p in data], ["A Paper"])

    def test_full_mapping(self):
        self.assertListEqual(
            self.parse(
                {"citation": [{"@id": "#paper"}]},
                [
                    {
                        "@id": "#paper",
                        "@type": "ScholarlyArticle",
                        "name": "A Paper",
                        "author": [{"@id": "#a"}, {"@id": "#b"}],
                        "datePublished": "2024-05-01",
                        "identifier": "https://doi.org/10.1145/1.2",
                        "url": "https://example.org/p.pdf",
                        "isPartOf": {"@id": "#venue"},
                    },
                    {"@id": "#a", "@type": "Person", "name": "Doe, J."},
                    {"@id": "#b", "@type": "Person", "name": "Roe, R."},
                    {"@id": "#venue", "@type": "Periodical", "name": "SC24"},
                ],
            ),
            [
                {
                    "title": "A Paper",
                    "authors": "Doe, J.; Roe, R.",
                    "venue": "SC24",
                    "year": "2024",
                    # Passed through as-is; the serializer strips the resolver
                    "doi": "https://doi.org/10.1145/1.2",
                    "url": "https://example.org/p.pdf",
                }
            ],
        )

    def test_year_only_date(self):
        got = self.parse(
            {"citation": [{"@id": "#p"}]},
            [{"@id": "#p", "name": "P", "datePublished": "1999"}],
        )
        self.assertEqual(got[0]["year"], "1999")


class TestImportEnvironmentSetup(SimpleTestCase):
    gpu = {
        "@id": "#gpu",
        "@type": "SoftwareApplication",
        "name": "GPU node",
        "trovi_type": "single_node",
    }
    arguments = {"site": "CHI@TACC", "lease_duration_hours": 4}

    def parse(self, applications, extra_entities):
        crate = build_crate({"actionApplication": applications}, extra_entities)
        return import_crate(crate)["version"]["environment_setup"]

    def test_singular_application(self):
        # RO-Crate only allows objects that are entities, so arguments are JSON text
        self.assertListEqual(
            self.parse(
                {"@id": "#gpu"},
                [self.gpu | {"trovi_arguments": json.dumps(self.arguments)}],
            ),
            [{"type": "single_node", "arguments": self.arguments, "label": "GPU node"}],
        )

    def test_object_arguments_are_rejected(self):
        with self.assertRaises(drf_exceptions.ValidationError):
            self.parse([{"@id": "#gpu"}], [self.gpu | {"trovi_arguments": {"a": 1}}])

    def test_several_setups_keep_their_order(self):
        cpu = {
            "@id": "#cpu",
            "@type": "SoftwareApplication",
            "trovi_type": "jupyterhub",
        }
        setups = self.parse([{"@id": "#gpu"}, {"@id": "#cpu"}], [self.gpu, cpu])
        self.assertListEqual(
            [(s["type"], s["label"]) for s in setups],
            [("single_node", "GPU node"), ("jupyterhub", "")],
        )

    def test_invalid_json_arguments(self):
        with self.assertRaises(drf_exceptions.ValidationError):
            self.parse([{"@id": "#gpu"}], [self.gpu | {"trovi_arguments": "{site"}])

    def test_imported_setups_validate(self):
        setups = self.parse(
            [{"@id": "#gpu"}],
            [self.gpu | {"trovi_arguments": json.dumps(self.arguments)}],
        )
        context = {"request": DummyRequest(data={}, auth=None, query_params={})}
        serializer = ArtifactVersionSetupSerializer(
            data=setups, many=True, context=context
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)


class TestImportedMetadataIsAccepted(TestCase):
    """
    The mapping is only useful if what it produces actually validates, so this
    round-trips parsed crate data through the serializer that the import view
    hands it to.
    """

    def test_parsed_crate_creates_artifact(self):
        crate = build_crate(
            {
                "video": [{"@id": "https://youtu.be/xyz"}],
                "citation": [{"@id": "#p"}],
            },
            [
                {"@id": "https://youtu.be/xyz", "@type": "VideoObject"},
                {
                    "@id": "#p",
                    "name": "A Paper",
                    "identifier": "10.1145/3.4",
                    "datePublished": "2023",
                    "url": "https://example.org/p.pdf",
                },
            ],
        )
        artifact_data = import_crate(crate)

        # The child serializers are @allow_force-decorated, so they need a
        # request in context, though this one carries no token
        context = {"request": DummyRequest(data={}, auth=None, query_params={})}
        for serializer_class, key in (
            (ArtifactVideoSerializer, "videos"),
            (ArtifactPublicationSerializer, "publications"),
        ):
            serializer = serializer_class(
                data=artifact_data[key], many=True, context=context
            )
            self.assertTrue(serializer.is_valid(), serializer.errors)

        artifact = Artifact.objects.create(
            title="Imported",
            short_description="s",
            long_description="l",
            owner_urn="urn:trovi:user:chameleon:someone@example.org",
        )
        for video in artifact_data["videos"]:
            artifact.videos.create(**video)
        for publication in artifact_data["publications"]:
            artifact.publications.create(**publication)

        self.assertEqual(
            [v.url for v in artifact.videos.all()], ["https://youtu.be/xyz"]
        )
        publication = artifact.publications.get()
        self.assertEqual(publication.title, "A Paper")
        self.assertEqual(publication.doi, "10.1145/3.4")
        self.assertEqual(publication.year, 2023)


class TestImportRepository(SimpleTestCase):
    def test_missing_crate(self):
        with self.assertRaisesMessage(drf_exceptions.ValidationError, "has no trovi"):
            import_crate(None)

    def test_blank_keywords_are_skipped(self):
        self.assertListEqual(import_crate(build_crate({"keywords": ""}))["tags"], [])


class TestImportDescription(SimpleTestCase):
    readme = {"@id": "README.md", "@type": "File"}

    def parse(self, files):
        crate = build_crate(
            {"description": {"@id": "README.md"}, "hasPart": [{"@id": "README.md"}]},
            [self.readme],
        )
        return import_crate(crate, files)["long_description"]

    def test_text(self):
        description = import_crate(build_crate({"description": "Some text"}))
        self.assertEqual(description["long_description"], "Some text")

    def test_readme(self):
        self.assertEqual(
            self.parse({"README.md": "# Title\n\nBody"}), "# Title\n\nBody"
        )

    def test_long_readme_is_cut_at_a_paragraph(self):
        readme = "Intro\n\n```\n" + "a line of code\n\n" * 1000
        description = self.parse({"README.md": readme})

        self.assertLessEqual(
            len(description), settings.ARTIFACT_LONG_DESCRIPTION_MAX_CHARS
        )
        self.assertTrue(
            description.endswith(
                f"\n```\n\n[Read the rest]({REPO}/blob/{'0' * 40}/README.md)"
            )
        )
        self.assertEqual(description.count("```") % 2, 0)

    def test_missing_readme(self):
        with self.assertRaisesMessage(drf_exceptions.ValidationError, "README.md"):
            self.parse({})


class TestExport(TestCase):
    def setUp(self):
        self.artifact = Artifact.objects.create(
            title="Exported",
            short_description="Short",
            long_description="Long",
            owner_urn="urn:trovi:user:chameleon:owner",
            visibility=Artifact.Visibility.PUBLIC,
        )
        for tag in ["one", "two"]:
            self.artifact.tags.add(ArtifactTag.objects.create(tag=tag))
        ArtifactAuthor.objects.create(
            artifact=self.artifact, full_name="Alice", affiliation="UC", email="a@b.co"
        )
        ArtifactVideo.objects.create(artifact=self.artifact, url="https://youtu.be/abc")
        ArtifactPublication.objects.create(
            artifact=self.artifact,
            title="A Paper",
            authors="Alice; Bob",
            venue="SC",
            year=2024,
            doi="10.1145/3.4",
            url="https://example.org/p.pdf",
        )
        self.version = ArtifactVersion.objects.create(
            artifact=self.artifact,
            contents_urn=f"urn:trovi:contents:git:{REPO}.git@main",
        )
        self.setups = [
            {"type": "jupyterhub", "arguments": {}, "label": ""},
            {
                "type": "single_node",
                "arguments": {"site": "CHI@UC", "lease_duration_hours": 4},
                "label": "GPU node",
            },
        ]
        for setup in self.setups:
            ArtifactVersionSetup.objects.create(artifact_version=self.version, **setup)

    def test_round_trip(self):
        data = import_crate(artifact_crate(self.artifact, self.version, None))

        self.assertEqual(
            (data["title"], data["short_description"], data["long_description"]),
            ("Exported", "Short", "Long"),
        )
        self.assertCountEqual(data["tags"], ["one", "two"])
        self.assertListEqual(
            data["authors"],
            [{"full_name": "Alice", "email": "a@b.co", "affiliation": "UC"}],
        )
        self.assertListEqual(data["videos"], [{"url": "https://youtu.be/abc"}])
        self.assertListEqual(
            data["publications"],
            [
                {
                    "title": "A Paper",
                    "authors": "Alice; Bob",
                    "venue": "SC",
                    "year": "2024",
                    "doi": "10.1145/3.4",
                    "url": "https://example.org/p.pdf",
                }
            ],
        )
        self.assertListEqual(data["version"]["environment_setup"], self.setups)

    def test_round_trip_without_authors_or_tags(self):
        self.artifact.tags.clear()
        self.artifact.authors.all().delete()

        data = import_crate(artifact_crate(self.artifact, None, None))

        self.assertEqual((data["tags"], data["authors"]), ([], []))
        self.assertListEqual(data["version"]["environment_setup"], [])

    def test_readme_as_description(self):
        crate = artifact_crate(self.artifact, self.version, "README.md")

        data = import_crate(crate, {"README.md": "From the README"})

        self.assertEqual(data["long_description"], "From the README")

    def export(self, query="", **kwargs):
        return self.client.get(
            reverse("import-detail", args=[self.artifact.uuid]) + query, **kwargs
        )

    def test_endpoint(self):
        response = self.export("?readme=README.md")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        root = next(e for e in response.json()["@graph"] if e["@id"] == "./")
        self.assertEqual(root["description"], {"@id": "README.md"})
        self.assertEqual(len(root["actionApplication"]), 2)

    def test_endpoint_version(self):
        older = ArtifactVersion.objects.create(
            artifact=self.artifact, contents_urn=f"urn:trovi:contents:git:{REPO}.git@v0"
        )
        # Versions made in the same instant would tie for the latest
        ArtifactVersion.objects.filter(pk=older.pk).update(
            created_at=self.version.created_at.replace(year=2000)
        )
        older.refresh_from_db()

        latest = self.export().json()
        chosen = self.export(f"?version={older.slug}").json()

        def setups(crate):
            root = next(e for e in crate["@graph"] if e["@id"] == "./")
            return root.get("actionApplication", [])

        self.assertEqual(len(setups(latest)), 2)
        self.assertEqual(setups(chosen), [])
        self.assertEqual(
            self.export("?version=missing").status_code, status.HTTP_404_NOT_FOUND
        )

    def test_endpoint_hides_private_artifacts(self):
        self.artifact.visibility = Artifact.Visibility.PRIVATE
        self.artifact.save()

        self.assertIn(
            self.export().status_code,
            (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
        )

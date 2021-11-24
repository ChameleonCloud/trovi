"""
Helper data classes used for dot-referencing API responses
Not meant to be robust, and mostly unvalidated, but helpful to avoid
having to reference dicts with strings repeatedly in tests.
"""
from uuid import UUID


class DummyArtifactLink:
    def __init__(self, label: str = None, verified: bool = None, urn: str = None):
        if any(f is None for f in (label, verified, urn)):
            raise ValueError("Invalid Artifact Link from API Response")
        self.label = label
        self.verified = verified
        self.urn = urn


class DummyArtifactVersion:
    def __init__(
        self,
        slug: str = None,
        created_at: str = None,
        contents: dict = None,
        metrics: dict = None,
        links: list[dict] = None,
    ):
        if any(f is None for f in (slug, created_at, contents, metrics, links)):
            raise ValueError("Invalid Artifact Version from API Response")
        self.slug = slug
        self.created_at = created_at
        self.contents_urn = contents["urn"]
        self.access_count = metrics["access_count"]
        self.links = [DummyArtifactLink(**link) for link in links]


class DummyArtifactAuthor:
    def __init__(
        self, full_name: str = None, affiliation: str = None, email: str = None
    ):
        if any(f is None for f in (full_name, email)):
            raise ValueError("Invalid Artifact Author from API Response")
        self.full_name = full_name
        self.affiliation = affiliation
        self.email = email


class DummyArtifact:
    def __init__(
        self,
        id: UUID = None,
        created_at: str = None,
        updated_at: str = None,
        title: str = None,
        short_description: str = None,
        long_description: str = None,
        tags: list[str] = None,
        authors: list[dict] = None,
        visibility: str = None,
        linked_projects: list[str] = None,
        reproducibility: dict = None,
        versions: dict = None,
    ):
        # Verify all required fields are provided
        if any(
            f is None
            for f in (
                id,
                created_at,
                updated_at,
                title,
                short_description,
                tags,
                authors,
                visibility,
                linked_projects,
                reproducibility,
                versions,
            )
        ):
            raise ValueError("Invalid Artifact API Response")
        self.uuid = id
        self.created_at = created_at
        self.updated_at = updated_at
        self.title = title
        self.short_description = short_description
        self.long_description = long_description
        self.tags = tags
        self.authors = [DummyArtifactAuthor(**author) for author in authors]
        self.visibility = visibility
        self.linked_projects = linked_projects
        self.is_reproducible: bool = reproducibility["enable_requests"]
        self.repro_access_hours: int = reproducibility["access_hours"]
        self.versions = [DummyArtifactVersion(**version) for version in versions]

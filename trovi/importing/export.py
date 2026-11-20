import json
from typing import Optional

from django.conf import settings

from trovi.models import Artifact, ArtifactVersion
from util.types import JSON

CONTEXT = "https://w3id.org/ro/crate/1.1/context"


def artifact_crate(
    artifact: Artifact, version: Optional[ArtifactVersion], readme: Optional[str]
) -> dict[str, JSON]:
    """
    Returns the trovi.json RO-Crate that imports as the artifact, with the launch
    options of version. With readme, the description is that file in the
    repository instead of the artifact's long description.
    """
    root = {
        "@id": "./",
        "@type": "Dataset",
        "name": artifact.title,
        "disambiguatingDescription": artifact.short_description,
        "description": {"@id": readme} if readme else artifact.long_description,
        "keywords": ", ".join(tag.tag for tag in artifact.tags.all()),
        # The importer reads authors even when there are none
        "author": [],
    }
    entities = []

    def add(prop: str, entity: dict[str, JSON]) -> None:
        root.setdefault(prop, []).append({"@id": entity["@id"]})
        entities.append(entity)

    if readme:
        add("hasPart", {"@id": readme, "@type": "File"})
    for i, author in enumerate(artifact.authors.all()):
        add(
            "author",
            {
                "@id": f"#author-{i}",
                "@type": "Person",
                "name": author.full_name,
                "email": author.email,
                "affiliation": author.affiliation,
            },
        )
    for i, setup in enumerate(version.setupSteps.all() if version else []):
        add(
            "actionApplication",
            {
                "@id": f"#launch-{i}",
                "@type": "SoftwareApplication",
                "name": setup.label,
                "trovi_type": setup.type,
                # RO-Crate only allows entities as object values
                "trovi_arguments": json.dumps(setup.arguments),
            },
        )
    for video in artifact.videos.all():
        add("video", {"@id": video.url, "@type": "VideoObject"})
    for i, publication in enumerate(artifact.publications.all()):
        citation = {
            "@id": f"#publication-{i}",
            "@type": "ScholarlyArticle",
            "name": publication.title,
            "author": [],
        }
        for j, name in enumerate(filter(None, publication.authors.split("; "))):
            citation["author"].append({"@id": f"#publication-{i}-author-{j}"})
            entities.append(
                {"@id": f"#publication-{i}-author-{j}", "@type": "Person", "name": name}
            )
        if publication.venue:
            citation["isPartOf"] = {"@id": f"#publication-{i}-venue"}
            entities.append(
                {
                    "@id": f"#publication-{i}-venue",
                    "@type": "Periodical",
                    "name": publication.venue,
                }
            )
        for prop, value in [
            ("datePublished", publication.year and str(publication.year)),
            ("identifier", publication.doi),
            ("url", publication.url),
        ]:
            if value:
                citation[prop] = value
        add("citation", citation)

    metadata = {
        "@id": settings.RO_CRATE_FILENAME,
        "@type": "CreativeWork",
        "about": {"@id": "./"},
        "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
    }
    return {"@context": CONTEXT, "@graph": [metadata, root, *entities]}

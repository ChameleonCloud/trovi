import logging
import re
from datetime import datetime
from typing import Hashable

import requests
from django.conf import settings

from trovi.models import ArtifactVersion
from trovi.storage.backends import StorageBackend
from util.types import JSON, ReadableBuffer

LOG = logging.getLogger(__name__)

ZENODO_URL = settings.ZENODO_URL


class ZenodoClient:
    class Endpoint:
        LOOKUP = "records/{}"
        CREATE = "deposit/depositions"
        UPDATE = "deposit/depositions/{}"
        FILE_UPLOAD = "deposit/depositions/{}/files"
        FILE = "deposit/depositions/{}/files/{}"
        NEW_VERSION = "deposit/depositions/{}/actions/newversion"
        PUBLISH = "deposit/depositions/{}/actions/publish"

    def __init__(self, access_token: str = None):
        self.access_token = access_token

    def _make_request(self, path: str, **kwargs) -> dict[str, JSON]:
        headers = kwargs.pop("headers", {"accept": "application/json"})
        if self.access_token:
            headers["authorization"] = "Bearer {}".format(self.access_token)
        res = requests.request(
            method=kwargs.pop("method", "GET"),
            url="{}/api/{}".format(settings.ZENODO_URL, path),
            headers=headers,
            **kwargs,
        )
        if res.status_code > 299:
            LOG.error(res.text)
        res.raise_for_status()
        return res.json() if res.status_code != 204 else None

    def get_versions(self, doi: str) -> list[dict[str, JSON]]:
        record = self._make_request("records/{}".format(ZenodoClient.to_record(doi)))
        search_result = self._make_request(
            "records",
            params={
                "q": 'conceptdoi:"{}"'.format(record["conceptdoi"]),
                "all_versions": True,
            },
        )

        versions = None
        # Zenodo seems to return a list of results when requesting via
        # 'requests' library, yet returns a wrapped standard Elasticsearch
        # response otherwise (e.g., with cURL). Assume either could happen.
        if isinstance(search_result, list):
            versions = search_result
        elif "hits" in search_result:
            versions = search_result.get("hits", {}).get("hits", [])

        if not versions:
            raise ValueError(
                "Got invalid response when fetching all versions for {}".format(doi)
            )

        return versions

    def create_deposition(
        self, metadata: "DepositionMetadata" = None, file: ReadableBuffer = None
    ) -> tuple[JSON, JSON]:
        res_json = self._make_request(
            self.Endpoint.CREATE,
            method="POST",
            json=metadata.to_payload(),
        )

        deposition_id = res_json.get("id")
        if not deposition_id:
            raise ValueError("Malformed response from Zenodo")

        self._make_request(
            self.Endpoint.FILE_UPLOAD.format(deposition_id),
            method="POST",
            files={"file": ("archive.tar.gz", file, "application/tar+gz")},
        )
        LOG.debug("Uploaded file for record {}".format(deposition_id))

        res_json = self._make_request(
            self.Endpoint.PUBLISH.format(deposition_id),
            method="POST",
        )
        LOG.debug("Published record {}".format(deposition_id))

        return res_json.get("doi"), res_json.get("conceptdoi")

    def new_deposition_version(
        self,
        metadata: "DepositionMetadata" = None,
        doi: str = None,
        file: ReadableBuffer = None,
    ) -> JSON:
        if not (metadata and doi and file):
            raise ValueError(
                'Missing required arguments, "metadata", "doi", and "file" are required'
            )

        record = ZenodoClient.to_record(doi)

        # Get latest version
        res_json = self._make_request(
            self.Endpoint.LOOKUP.format(record),
            method="GET",
        )
        latest_url = res_json.get("links", {}).get("latest")
        if not latest_url:
            raise ValueError(
                "Could not discover latest version for deposition {}".format(doi)
            )
        latest_record = latest_url.split("/")[-1]

        # Start new draft
        res_json = self._make_request(
            self.Endpoint.NEW_VERSION.format(latest_record),
            method="POST",
        )
        draft_url = res_json.get("links", {}).get("latest_draft")
        if not draft_url:
            raise ValueError(
                "Could not find created version draft for record {}".format(
                    latest_record
                )
            )
        draft_record = draft_url.split("/")[-1]

        # Update draft metadata
        res_json = self._make_request(
            self.Endpoint.UPDATE.format(draft_record),
            method="PUT",
            json=metadata.to_payload(),
        )
        LOG.debug("Updated metadata for record {}".format(draft_record))

        # Delete all files first; cannot update in-place
        for f in res_json.get("files"):
            self._make_request(
                self.Endpoint.FILE.format(draft_record, f["id"]),
                method="DELETE",
            )
            LOG.debug("Deleted file {} for record {}".format(f["id"], draft_record))

        # Upload file contents
        self._make_request(
            self.Endpoint.FILE_UPLOAD.format(draft_record),
            method="POST",
            files={"file": ("archive.tar.gz", file, "application/tar+gz")},
        )
        LOG.debug("Uploaded file for record {}".format(draft_record))

        # Publish draft
        res_json = self._make_request(
            self.Endpoint.PUBLISH.format(draft_record),
            method="POST",
        )
        LOG.debug("Published record {}".format(draft_record))

        return res_json.get("doi")

    @staticmethod
    def to_record(doi: str) -> str:
        if not doi:
            raise ValueError("No DOI provided")
        elif not re.match(r"10\.[0-9]+/zenodo\.[0-9]+$", doi):
            raise ValueError("DOI is invalid (wrong format)")
        else:
            return doi.split(".")[-1]

    @staticmethod
    def to_record_url(doi: str) -> str:
        record = ZenodoClient.to_record(doi)
        return "{}/record/{}".format(settings.ZENODO_URL, record)

    def get_files(self, doi: str) -> JSON:
        record = ZenodoClient.to_record(doi)
        res_json = self._make_request(self.Endpoint.FILE.format(record), method="GET")
        LOG.debug(f"Fetched files for {doi}")
        return res_json.get("files")


class DepositionMetadata:
    def __init__(
        self,
        title: str = None,
        description: str = None,
        creators: list[dict[str, str]] = None,
        upload_type: str = None,
        publication_type: str = None,
        publication_date: datetime = None,
        communities: list[dict[str, JSON]] = None,
        keywords: list[str] = None,
    ):
        self.title = title
        self.description = description
        self.creators = creators
        self.upload_type = upload_type
        self.publication_type = publication_type
        self.publication_date = publication_date
        self.communities = communities
        self.keywords = keywords

    def to_payload(self) -> dict[str, JSON]:
        """Convert to a JSON payload compatible with Zenodo's deposition API."""
        return {
            "metadata": {
                "title": self.title,
                "description": self.description,
                "creators": [
                    # Default affiliation to empty string to satisfy validation
                    {"name": c["name"], "affiliation": c["affiliation"] or ""}
                    for c in self.creators
                ],
                "upload_type": self.upload_type,
                "publication_type": self.publication_type,
                "publication_date": (
                    datetime.strftime(self.publication_date, "%Y-%m-%d")
                ),
                "communities": self.communities or [],
                "keywords": self.keywords or [],
            },
        }

    @classmethod
    def from_version(cls, artifact_version: ArtifactVersion):
        artifact = artifact_version.artifact
        keywords = ["chameleon"].extend([str(label) for label in artifact.tags.all()])
        return cls(
            title=artifact.title,
            description=artifact.short_description,
            creators=[
                {"name": a.name, "affiliation": a.affiliation}
                for a in list(artifact.authors.all())
            ],
            upload_type="publication",
            publication_type="workingpaper",
            publication_date=artifact_version.created_at,
            communities=[{"identifier": "chameleon"}],
            keywords=keywords,
        )


class ZenodoBackend(StorageBackend):
    def __init__(self, name: str, version: ArtifactVersion, *args, **kwargs):
        super(ZenodoBackend, self).__init__(name, *args, **kwargs)
        self.zenodo = ZenodoClient(access_token=settings.ZENODO_DEFAULT_ACCESS_TOKEN)
        self.version = version
        if not self.content_id:
            if version.has_doi():
                self.content_id = version.contents_urn.split(":")[-1]
            elif version.artifact.has_doi():
                self.content_id = next(
                    (v for v in version.artifact.versions.all() if v.has_doi()), None
                ).contents_urn.split(":")[-1]

    def update_size(self) -> int:
        if not self.content_id:
            return 0
        files = self.zenodo.get_files(self.content_id)
        if not isinstance(files, list):
            raise IOError("Got invalid files from Zenodo")
        return sum(f["filesize"] for f in files)

    def generate_content_id(self) -> Hashable:
        dep = self.zenodo.create_deposition(
            DepositionMetadata.from_version(self.version)
        )
        return dep[0]

    def cleanup(self):
        pass

    def update_closed_status(self) -> bool:
        pass

    def write_segment(self, buffer: ReadableBuffer) -> int:
        pass

    def writable(self) -> bool:
        return True

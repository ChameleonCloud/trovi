from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional

import requests
from django.conf import settings
from requests import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError

from trovi.models import ArtifactVersion
from trovi.storage.backends import StorageBackend
from trovi.storage.links.http import HttpDownloadLink
from util.types import JSON, ReadableBuffer

LOG = logging.getLogger(__name__)

ZENODO_URL = settings.ZENODO_URL


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
                {"name": a.full_name, "affiliation": a.affiliation}
                for a in artifact.authors.all()
            ],
            upload_type="publication",
            publication_type="workingpaper",
            publication_date=artifact_version.created_at,
            communities=[{"identifier": "chameleon"}],
            keywords=keywords,
        )


class ZenodoBackend(StorageBackend):
    class Endpoint:
        LOOKUP = "records/{}"
        CREATE = "deposit/depositions"
        UPDATE = "deposit/depositions/{}"
        FILE_UPLOAD = "deposit/depositions/{}/files"
        FILE = "deposit/depositions/{}/files/{}"
        NEW_VERSION = "deposit/depositions/{}/actions/newversion"
        PUBLISH = "deposit/depositions/{}/actions/publish"

    def __init__(self, name: str, version: ArtifactVersion, *args, **kwargs):
        super(ZenodoBackend, self).__init__(name, *args, **kwargs)
        self.access_token = settings.ZENODO_DEFAULT_ACCESS_TOKEN
        self.version = version
        if not self.content_id:
            if version.has_doi():
                self.content_id = version.contents_urn.split(":")[-1]

    def update_length(self) -> int:
        if not self.content_id:
            return 0
        files = self.get_files()
        if not isinstance(files, list):
            raise IOError("Got invalid files from Zenodo")
        return sum(f["filesize"] for f in files)

    def generate_content_id(self):
        return None

    def download(self):
        files = self.get_files()
        print(files)

    def upload(self):
        meta = DepositionMetadata.from_version(self.version)
        if not self.content_id:
            self.create_deposition(meta, file=self.buffer)
        else:
            self.new_deposition_version(meta, self.content_id, self.buffer)

    def cleanup(self):
        pass

    def writable(self) -> bool:
        return not self.closed

    def to_record(self) -> str:
        if not self.content_id:
            raise ValueError("No DOI provided")
        elif not re.match(r"10\.[0-9]+/zenodo\.[0-9]+$", self.content_id):
            raise ValueError("DOI is invalid (wrong format)")
        else:
            return self.content_id.split(".")[-1]

    def get_files(self) -> JSON:
        record = self.to_record()
        res_json = self._make_request(self.Endpoint.FILE.format(record), method="GET")
        LOG.debug(f"Fetched files for {self.content_id}")
        return res_json.get("files")

    def _make_request(
        self, path: str, raw: bool = False, **kwargs
    ) -> dict[str, JSON] | None | Response:
        headers = kwargs.pop("headers", {"accept": "application/json"})
        if self.access_token:
            headers["authorization"] = f"Bearer {self.access_token}"
        res = requests.request(
            method=kwargs.pop("method", "GET"),
            url=f"{settings.ZENODO_URL}/api/{path}",
            headers=headers,
            **kwargs,
        )
        if res.status_code > 299:
            LOG.error(res.text)
        res.raise_for_status()
        if res.status_code == status.HTTP_204_NO_CONTENT:
            return None
        if raw:
            return res
        else:
            return res.json()

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

        self.content_id = res_json.get("doi")

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

        record = ZenodoBackend.to_record(doi)

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
            files={
                "file": (
                    "archive.tar.gz",
                    self.buffer,
                    "application/tar+gz",
                )
            },
        )

        LOG.debug("Uploaded file for record {}".format(draft_record))

        # Publish draft
        res_json = self._make_request(
            self.Endpoint.PUBLISH.format(draft_record),
            method="POST",
        )
        LOG.debug("Published record {}".format(draft_record))

        self.content_id = res_json.get("doi")

    def to_record_url(self) -> str:
        record = self.to_record()
        return f"{settings.ZENODO_URL}/records/{record}"

    def get_temporary_download_url(self) -> Optional[HttpDownloadLink]:
        # Legacy archives will be archive.zip, so we have to determine which is right
        record_url = self.to_record_url()
        tar_url = f"{record_url}/files/archive.tar.gz?download=1"
        zip_url = f"{record_url}/files/archive.zip?download=1"

        # See if the tar archive exists
        tar_response = requests.head(tar_url, allow_redirects=True)
        if tar_response.ok:
            download_url = tar_url
        else:
            download_url = zip_url
        return HttpDownloadLink(
            url=download_url,
            headers={},
            method="GET",
            exp=datetime.max,
        )

import os
import re
import subprocess
from typing import Optional
from urllib.parse import quote

import requests
from giturlparse import parse

# Hosts whose repositories the git storage backend can serve
GIT_HOSTS = ("github.com", "gitlab.com")
ZENODO_RECORD = re.compile(r"^https?://(?:www\.)?zenodo\.org/records?/(\d+)(?:[/?#]|$)")
ARCHIVE_SUFFIXES = (".zip", ".tar.gz", ".tgz", ".tar")


class ContentsUnavailable(Exception):
    """Contents can't be looked up now, for the reason in the message"""


def parse_project_urn(project_urn):
    provider, project_id = project_urn.split(":", 4)[3:]
    return {
        "provider": provider,
        "id": project_id,
    }


def parse_owner_urn(owner_urn):
    provider, owner_id = owner_urn.split(":", 4)[3:]
    return {
        "provider": provider,
        "id": owner_id,
    }


def parse_contents_urn(contents_urn):
    provider, contents_id = contents_urn.split(":", 4)[3:]
    return {
        "provider": provider,
        "id": contents_id,
    }


def latest_commit(remote: str) -> str:
    """
    Returns the latest commit on the default branch of the git repository at
    remote, and raises ContentsUnavailable if it can't be reached.
    """
    try:
        return subprocess.run(
            ["git", "ls-remote", "--exit-code", remote, "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
            # Private and missing repositories would ask for credentials
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        ).stdout.split()[0]
    except (OSError, subprocess.SubprocessError, IndexError) as e:
        raise ContentsUnavailable(f"looking up {remote} failed: {e}")


def git_contents_urn(url: str) -> Optional[str]:
    """
    Returns a contents URN for the latest commit on the default branch of the
    repository that url points into, or None if url isn't on a host in GIT_HOSTS.
    Paths within the repository, such as /tree/main/docs, are dropped. Raises
    ContentsUnavailable if the repository can't be reached.
    """
    # giturlparse only recognizes the bare hosts, and keeps the path otherwise
    parsed = parse(url.replace("://www.", "://", 1))
    if not parsed.valid or parsed.host not in GIT_HOSTS:
        return None
    path = "/".join(filter(None, [parsed.owner, parsed.groups_path, parsed.repo]))
    remote = f"https://{parsed.host}/{path}.git"
    return f"urn:trovi:contents:git:{remote}@{latest_commit(remote)}"


def launch_contents_urn(source_url: str) -> Optional[str]:
    """
    Returns contents to launch for an artifact crawled from source_url: the latest
    commit of its git repository, or the one archive in its Zenodo record. Returns
    None if it has neither, and raises ContentsUnavailable if they can't be looked
    up.
    """
    if urn := git_contents_urn(source_url):
        return urn
    match = ZENODO_RECORD.match(source_url)
    if not match:
        return None
    record = f"https://zenodo.org/records/{match[1]}"
    try:
        response = requests.get(
            f"https://zenodo.org/api/records/{match[1]}", timeout=30
        )
        response.raise_for_status()
        keys = [f["key"] for f in response.json()["files"]]
    except (requests.RequestException, ValueError, KeyError, TypeError) as e:
        raise ContentsUnavailable(f"looking up {record} failed: {e}")
    archives = [key for key in keys if key.lower().endswith(ARCHIVE_SUFFIXES)]
    if len(archives) != 1:
        return None
    return f"urn:trovi:contents:http:{record}/files/{quote(archives[0])}?download=1"

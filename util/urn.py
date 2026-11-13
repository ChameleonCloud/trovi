from typing import Optional

from giturlparse import parse

# Hosts whose repositories the git storage backend can serve
GIT_HOSTS = ("github.com", "gitlab.com")


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


def git_contents_urn(url: str) -> Optional[str]:
    """
    Returns a contents URN for the default branch of the repository that url points
    into, or None if url isn't on a host in GIT_HOSTS. Paths within the repository,
    such as /tree/main/docs, are dropped.
    """
    # giturlparse only recognizes the bare hosts, and keeps the path otherwise
    parsed = parse(url.replace("://www.", "://", 1))
    if not parsed.valid or parsed.host not in GIT_HOSTS:
        return None
    path = "/".join(filter(None, [parsed.owner, parsed.groups_path, parsed.repo]))
    return f"urn:trovi:contents:git:https://{parsed.host}/{path}.git"

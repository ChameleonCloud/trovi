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

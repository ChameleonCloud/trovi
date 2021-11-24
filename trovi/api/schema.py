import jsonschema

from trovi.fields import URNField
from trovi.models import ArtifactAuthor

SchemaValidator = jsonschema.Draft202012Validator

CreateArtifactSchema = SchemaValidator(
    {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "short_description": {"type": "string"},
            "long_description": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "authors": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "full_name": {"type": "string"},
                        "affiliation": {"type": "string"},
                        "email": {"type": "string", "format": "email"},
                    },
                    "required": ["full_name", "email"],
                    "additionalProperties": False,
                },
            },
            "visibility": {
                "type": "string",
                "enum": ["public", "private"],
                "default": "private",
            },
            "linked_projects": {
                "type": "array",
                "items": {"type": "string", "format": "urn"},
            },
            "reproducibility": {
                "type": "object",
                "properties": {
                    "enable_requests": {"type": "boolean", "default": False},
                    "access_hours": {"type": "integer"},
                },
                "if": {
                    "properties": {"enable_requests": {"const": False}},
                },
                "then": {
                    "properties": {"access_hours": False},
                },
                "required": ["enable_requests"],
                "additionalProperties": False,
            },
            "version": {
                "type": "object",
                "properties": {
                    "contents": {
                        "type": "object",
                        "properties": {
                            "urn": {"type": "string", "format": "urn"},
                        },
                    },
                    "links": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "urn": {"type": "string", "format": "urn"},
                            },
                            "required": ["label", "urn"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["contents"],
                "additionalProperties": False,
            },
        },
        "required": ["title", "short_description"],
        "additionalProperties": False,
    }
)

# Describes a general JSON Pointer
jsonPointer = {"type": "string", "pattern": "^(/[^/~]*(~[01][^/~]*)*)*$"}
# Describes a JSON Pointer in terms of valid mutable paths in an Artifact
mutableJsonPointer = {
    "oneOf": [
        {"type": "string", "pattern": r"^/title$"},
        {"type": "string", "pattern": r"^/short_description$"},
        {"type": "string", "pattern": r"^/long_description$"},
        {"type": "string", "pattern": r"^/tags(/[0-9]+)?$"},
        {
            "type": "string",
            "pattern": rf"^/authors"
            rf"(/[0-9]+"
            rf"(/{'|'.join(map(str, ArtifactAuthor._meta.get_fields()))})?)?$",
        },
        {"type": "string", "pattern": r"^/visibility$"},
        {
            "type": "string",
            "pattern": rf"^/linked_projects"
            rf"(/[0-9]+(/{str(URNField.pattern.pattern)})?)?$",
        },
        {
            "type": "string",
            "pattern": r"^/reproducibility(/(enable_requests|access_hours))?$",
        },
    ]
}

# JSON Patch Operations
patchAdd = {
    "type": "object",
    "properties": {
        "op": {"enum": ["add"]},
        "path": mutableJsonPointer,
    },
    "required": ["op", "path", "value"],
    "additionalProperties": False,
}
patchRemove = {
    "type": "object",
    "properties": {
        "op": {"enum": ["remove"]},
        "path": {
            "oneOf": [
                mutableJsonPointer,
                {"type": "string", "pattern": "^/sharing_key$"},
            ]
        },
    },
    "required": ["op", "path"],
    "additionalProperties": False,
}
patchReplace = {
    "type": "object",
    "properties": {
        "op": {"enum": ["replace"]},
        "path": mutableJsonPointer,
    },
    "required": ["op", "path", "value"],
    "additionalValues": False,
}
patchMove = {
    "type": "object",
    "properties": {
        "op": {"enum": ["move"]},
        "from": mutableJsonPointer,
        "path": mutableJsonPointer,
    },
    "required": ["op", "from", "path"],
    "additionalProperties": False,
}
patchCopy = {
    "type": "object",
    "properties": {
        "op": {"enum": ["copy"]},
        "from": jsonPointer,
        "path": mutableJsonPointer,
    },
    "required": ["op", "from", "path"],
    "additionalProperties": False,
}

# Valid update fields are handled at the Schema level.
# This seemed like the easiest, strictest, and most non-redundant way to do it.
# The one thing this leaves to be desired is error messages,
# but that can be worked out in the future.
UpdateArtifactSchema = SchemaValidator(
    {
        "type": "array",
        "items": {
            "allOf": [
                {"oneOf": [patchAdd, patchRemove, patchReplace, patchMove, patchCopy]},
            ]
        },
    }
)

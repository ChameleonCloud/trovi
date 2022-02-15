import jsonschema

SchemaValidator = jsonschema.Draft202012Validator

version_schema = {
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
}

CreateArtifactVersionSchema = SchemaValidator(version_schema)
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
            "owner_urn": {"type": "string", "format": "urn"},
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
            "version": version_schema,
        },
        "required": ["title", "short_description"],
        "additionalProperties": False,
    }
)

# Describes a general JSON Pointer
jsonPointer = {"type": "string", "pattern": "^(/[^/~]*(~[01][^/~]*)*)*$"}

# JSON Patch Operations
patchAdd = {
    "type": "object",
    "properties": {
        "op": {"enum": ["add"]},
        "path": jsonPointer,
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
                jsonPointer,
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
        "path": jsonPointer,
    },
    "required": ["op", "path", "value"],
    "additionalValues": False,
}
patchMove = {
    "type": "object",
    "properties": {
        "op": {"enum": ["move"]},
        "from": jsonPointer,
        "path": jsonPointer,
    },
    "required": ["op", "from", "path"],
    "additionalProperties": False,
}
patchCopy = {
    "type": "object",
    "properties": {
        "op": {"enum": ["copy"]},
        "from": jsonPointer,
        "path": jsonPointer,
    },
    "required": ["op", "from", "path"],
    "additionalProperties": False,
}

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

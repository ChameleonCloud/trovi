import jsonschema

from trovi.common.tokens import TokenTypes

SchemaValidator = jsonschema.Draft202012Validator

jws = {
    "type": "string",
    "pattern": r"^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+(\.[A-Za-z0-9-_]+)?$",
}
supported_token_types = {
    # See https://datatracker.ietf.org/doc/html/rfc8693#section-3
    # for other token types that may be supported in the future
    "enum": [token.value for token in TokenTypes]
}
TokenGrantSchema = SchemaValidator(
    {
        "type": "object",
        "properties": {
            "grant_type": {"enum": ["token_exchange"]},
            "subject_token": jws,
            "subject_token_type": supported_token_types,
            "requested_token_type": supported_token_types,
            "scope": {
                "type": "string",
                "pattern": r"^\s*[A-Za-z0-9:-_]+(?:\s+[A-Za-z0-9:-_]+)*\s*$"
            },
            # The following properties are ignored, for now
            "resource": {"type": "string", "format": "URI"},
            "audience": {"type": "string"},
            "actor_token": jws,
            "actor_token_type": jws,
        },
        "if": {"properties": {"actor_token": {"const": None}}},
        "then": {"properties": {"actor_token_type": False}},
        "else": {"properties": {"actor_token_type": True}},
        "required": ["grant_type", "subject_token", "subject_token_type"],
        "additionalProperties": False,
    }
)

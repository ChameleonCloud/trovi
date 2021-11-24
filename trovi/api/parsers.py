import re

import jsonschema
from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser

from util.types import JSON


class JSONSchemaParser(JSONParser):
    """
    Functionally the same as a regular JSONParser, but accepts an optional schema
    to validate against.

    Schema should be in the form of a json-schema object (https://json-schema.org)
    and should be passed to the ``parse`` method via the ``parser_context`` parameter.
    """

    _schema_error_remove = re.compile(r"^(.*in schema)")

    def parse(
        self, stream: bytes, media_type=None, parser_context: dict = None
    ) -> JSON:
        parsed = super(JSONSchemaParser, self).parse(
            stream, media_type=media_type, parser_context=parser_context
        )
        action = parser_context["view"].action
        # This is good to throw, because it should only happen if we've made
        # a terrible programming error
        schema = parser_context["schema"].get(action)

        if schema:
            try:
                schema.validate(parsed)
            except jsonschema.ValidationError as e:
                # The error message includes the whole schema which can be very
                # large and unhelpful, so truncate it to be brief and useful
                details = str(e).split("\n")[:3]
                error_msg = f"Schema error: {details[0]}"
                schema_loc = self._schema_error_remove.sub("", details[-1])
                # SUPER hacky bracket-to-dot-notation thing
                schema_loc = schema_loc.replace("']", "").replace("['", ".")
                error_msg += f" (in '{schema_loc[:-1]}')"  # Strip trailing ':'
                raise ParseError(detail=error_msg)

        return parsed

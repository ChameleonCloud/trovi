from typing import Type, Any

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from jsonpatch import JsonPatch
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from trovi.fields import URNField
from util.types import JSON


class JsonPointerField(serializers.RegexField):
    regex = r"^(/[^/~]*(~[01][^/~]*)*)*$"

    def __init__(self, **kwargs):
        super(JsonPointerField, self).__init__(self.regex, **kwargs)


class URNSerializerField(serializers.RegexField):
    regex = URNField.pattern

    def __init__(self, **kwargs):
        super(URNSerializerField, self).__init__(self.regex, **kwargs)


@extend_schema_field(OpenApiTypes.ANY)
class AnyField(serializers.Field):
    def to_representation(self, value: Any) -> Any:
        return value

    def to_internal_value(self, data: Any) -> Any:
        return data


class JsonPatchOperationSerializer(serializers.Serializer):
    """
    Represents a JSON Patch for an Artifact
    """

    op = serializers.ChoiceField(
        choices=["add", "remove", "replace", "move", "copy"],
        required=True,
        write_only=True,
    )
    from_ = JsonPointerField(write_only=True, required=False)
    path = JsonPointerField(write_only=True, required=False)
    value = AnyField(write_only=True, required=False)

    op_arguments_map = {
        "add": ["path", "value"],
        "remove": ["path"],
        "replace": ["path", "value"],
        "move": ["from", "path"],
        "copy": ["from", "path"],
    }

    def __init__(self, patch_class: Type[JsonPatch] = JsonPatch, *args, **kwargs):
        self.patch_class = patch_class
        super(JsonPatchOperationSerializer, self).__init__(*args, **kwargs)

    def update(self, _, __):
        raise ValueError("Incorrect usage of JsonPatchSerializer (update)")

    def create(self, validated_data: dict[str, JSON]) -> dict[str, JSON]:
        return validated_data

    def get_fields(self) -> dict[str, serializers.Field]:
        fields = super(JsonPatchOperationSerializer, self).get_fields()
        from_ = fields.pop("from_", None)
        if from_ is not None:
            fields["from"] = from_
        return fields

    def validate(self, attrs: dict[str, JSON]) -> dict[str, JSON]:
        op = attrs.get("op")
        from_ = attrs.get("from")
        path = attrs.get("path")

        required_args = self.op_arguments_map[op]

        args_error = (
            f"Invalid arguments for op {op}. "
            f"Required arguments are {required_args}."
        )

        # Assert that all required args are supplied by the request
        if not all(arg in attrs for arg in required_args):
            raise ValidationError(args_error)

        # Assert that the only items supplied are the op and required args
        if len(attrs) != (len(required_args) + 1):
            raise ValidationError(args_error)

        if "sharing_key" == path and op != "remove":
            raise ValidationError(
                "sharing_key is not writable via patch/put. "
                "If you wish to change it, remove it and it will be regenerated."
            )
        if "sharing_key" == from_:
            raise ValidationError("sharing_key is not readable via patch/put.")

        return super(JsonPatchOperationSerializer, self).validate(attrs)

import logging
from typing import Type, Any, Callable, Optional

from django.conf import settings
from rest_framework.request import Request
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from jsonpatch import JsonPatch
from rest_framework import serializers
from rest_framework.exceptions import ValidationError, PermissionDenied

from trovi.common.tokens import JWT
from trovi.fields import URNField
from util.types import JSON

LOG = logging.getLogger(__name__)


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
    from_ = JsonPointerField(write_only=True, required=False, max_length=140)
    path = JsonPointerField(write_only=True, required=False, max_length=140)
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


def _is_valid_force_request(self: serializers.Serializer) -> bool:
    """
    Determines if a request wants to force an update. Ensures that the request is valid,
    and caches the result in the serializer's context.
    """
    if (already_forced := self.context.get("force")) is not None:
        return already_forced
    request = self.context.get("request")
    if not request:
        raise ValueError(
            "allow_force is only intended to be used on incoming API requests."
        )
    # If forced writes are enabled, and the user has requested one
    if (
        settings.ARTIFACT_ALLOW_ADMIN_FORCED_WRITES
        and request.query_params.get("force") is not None
    ):
        token = JWT.from_request(request)
        if not token:
            raise PermissionDenied("Unauthenticated user attempted to use ?force flag.")
        if token.is_admin():
            LOG.warning(f"Recorded a forced update from {token.to_urn()}")
            self.context.setdefault("force", True)
            return True
        else:
            raise PermissionDenied("Non-Admin users cannot use the ?force flag.")
    else:
        # The user has not requested a forced update
        self.context.setdefault("force", False)
        return False


def _validate_strict_schema(to_internal_value: Callable) -> Callable:
    """
    Decorator which causes serializers to reject any requests which have any fields
    in them which are not strictly writable
    """

    def wrapper(self: serializers.Serializer, data: dict[str, JSON]) -> dict[str, JSON]:
        if not isinstance(data, dict):
            # DRF validators should catch this later and throw the appropriate error
            return data
        unknown = set(data) - set(field.field_name for field in self._writable_fields)
        if _is_valid_force_request(self):
            internal = to_internal_value(self, data)
            # to_internal_value will remove all non-writable fields,
            # so we have to jam them back in
            internal.update({field: data[field] for field in unknown})
            return internal
        # We ignore this check for patches because of how JSON patch resolves
        # nested objects
        if unknown and not self.context.get("patch"):
            raise ValidationError(
                {
                    "Attempted to write invalid field(s)": list(unknown),
                    "in": self.field_name or ".",
                }
            )
        return to_internal_value(self, data)

    return wrapper


def _bypass_validation(is_valid: Callable) -> Callable:
    """
    Decorator which allows validation bypass via a ?force URL parameter

    Only bypasses API validation. Database validation still occurs. This is by design.
    """

    def wrapper(self: serializers.Serializer, **kwargs) -> bool:
        if _is_valid_force_request(self):
            # If this is a valid force request, bypass validation entirely
            self._validated_data = self.to_internal_value(self.initial_data)
            self._errors = {}
            return True
        else:
            # If the user has not requested a force write, call is_valid as normal
            return is_valid(self, **kwargs)

    return wrapper


def allow_force(
    serializer: Type[serializers.Serializer],
) -> Type[serializers.Serializer]:
    """
    Shortcut class decorator which wraps
    a serializer's is_valid method with a force bypass.
    """
    serializer.is_valid = _bypass_validation(serializer.is_valid)
    return serializer


def strict_schema(
    serializer: Type[serializers.Serializer],
) -> Type[serializers.Serializer]:
    """
    Shortcut class decorator which wraps a serializer's .to_internal_value method with
    a strict schema enforcer
    """
    serializer.to_internal_value = _validate_strict_schema(serializer.to_internal_value)
    return serializer


def get_user_urn_from_request(request: Request) -> Optional[str]:
    if not request:
        return None
    token = JWT.from_request(request)
    if not token:
        return None
    return token.to_urn()


def get_requesting_user_urn(serializer: serializers.Serializer) -> Optional[str]:
    """
    Generates a default owner URN based on the requesting user's auth token
    """
    return get_user_urn_from_request(serializer.context.get("request"))

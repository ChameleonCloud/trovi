"""
The classes in this file provide overrides to JSON Patch classes to ensure that
patches are valid specifically for our Trovi models.
"""

from collections import defaultdict
from types import MappingProxyType
from typing import Any

import jsonpatch
from rest_framework.exceptions import ValidationError

from util.types import JSONObject, JSON

patch_errors = defaultdict(list)


class ArtifactPatchMixin:
    """
    Provides helpers to all ArtifactPatchOperations
    """

    class walker(defaultdict):
        """
        This is a helper class which simply modifies defaultdict's default factory to
        accept the key as a parameter. This way, the key can be tested for desired
        properties while we are walking the paths in the patch.
        """

        def __missing__(self, key: Any) -> Any:
            self[key] = self.default_factory(key)
            return self[key]

    error_id = None
    INVALID_PATH = "I'm an invalid path because paths are only ever dict or None"
    _artifact_author_description = {
        "full_name": None,
        "email": None,
        "affiliation": None,
    }
    _artifact_link_description = {
        "relation": None,
        "linked_artifact": None,
    }

    def _int_key_only(self, desired_key: Any, value: Any = None) -> Any:
        """
        Helper function that ensures a defaultdict's key is only an integer.
        User for paths that are supposed to be lists.
        """
        # In JSON Patch syntax, "-" means "end of list"
        if desired_key == "-":
            return value
        try:
            int(desired_key)
            return value
        except ValueError:
            return self.INVALID_PATH

    def valid_mutable_path(self, operation: dict, path: list):
        """
        Walks a path to determine if it is valid for a mutable operation
        """
        # Describes paths within an Artifact obj that are allowed to be modified.
        # All valid paths will be handled by the JSON Patch library itself,
        # since invalid paths will not appear in the object.
        walk = defaultdict(
            (lambda: self.INVALID_PATH),
            {
                "title": None,
                "short_description": None,
                "long_description": None,
                "tags": self.walker(self._int_key_only),
                "authors": self.walker(
                    lambda a: self._int_key_only(a, self._artifact_author_description)
                ),
                # linked_projects is mutable, but only admins can modify it
                # this is enforced by the ArtifactSerializer
                "linked_projects": self.walker(self._int_key_only),
                "linked_artifacts": self.walker(
                    lambda a: self._int_key_only(a, self._artifact_link_description)
                ),
                "reproducibility": {"enable_requests": None, "access_hours": None},
                # owner_urn is mutable, but only current owners can modify it
                # this is enforced by the ArtifactSerializer
                "owner_urn": None,
                "visibility": None,
            },
        )
        error = (
            f"Write operation '{operation['op']}' does not have "
            f"valid mutable path: {path}"
        )
        for step in path:
            if walk is None:
                patch_errors[self.error_id].append(error)
                return False
            walk = walk[step]
            if walk == self.INVALID_PATH:
                patch_errors[self.error_id].append(error)
                return False
        return True


class ArtifactRemoveOperation(jsonpatch.RemoveOperation, ArtifactPatchMixin):
    def apply(self, obj: JSONObject) -> JSONObject:
        if self.pointer.parts != ["sharing_key"]:
            if not self.valid_mutable_path(self.operation, self.pointer.parts):
                raise ValidationError(f"{self.pointer.path} cannot be removed")
        return super(ArtifactRemoveOperation, self).apply(obj)


class ArtifactAddOperation(jsonpatch.AddOperation, ArtifactPatchMixin):
    def apply(self, obj: JSONObject) -> JSONObject:
        if not self.valid_mutable_path(self.operation, self.pointer.parts):
            raise ValidationError(f"{self.pointer.path} cannot be modified")
        return super(ArtifactAddOperation, self).apply(obj)


class ArtifactReplaceOperation(jsonpatch.ReplaceOperation, ArtifactPatchMixin):
    def apply(self, obj: JSONObject) -> JSONObject:
        if not self.valid_mutable_path(self.operation, self.pointer.parts):
            raise jsonpatch.JsonPatchException(
                f"{self.pointer.path} cannot be modified"
            )
        return super(ArtifactReplaceOperation, self).apply(obj)


class ArtifactMoveOperation(jsonpatch.MoveOperation, ArtifactPatchMixin):
    def apply(self, obj: JSONObject) -> JSONObject:
        if not self.valid_mutable_path(self.operation, self.pointer.parts):
            raise jsonpatch.JsonPatchException(
                f"{self.pointer.path} cannot be modified"
            )
        from_path = self.operation.get("from")
        if from_path:
            from_ptr = self.pointer_cls(from_path)
            if not self.valid_mutable_path(self.operation, from_ptr.parts):
                raise jsonpatch.JsonPatchException(
                    f"{self.pointer.path} cannot be removed"
                )
        return super(ArtifactMoveOperation, self).apply(obj)


class ArtifactCopyOperation(jsonpatch.CopyOperation, ArtifactPatchMixin):
    def apply(self, obj: JSONObject) -> JSONObject:
        if not self.valid_mutable_path(self.operation, self.pointer.parts):
            raise jsonpatch.JsonPatchException(
                f"{self.pointer.path} cannot be modified"
            )
        return super(ArtifactCopyOperation, self).apply(obj)


class ArtifactPatch(jsonpatch.JsonPatch):
    """
    Provides overrides for JsonPatch such that the object output is a diff
    of the original object after being patched,
    rather than the default behavior for jsonpatch which outputs
    the entire original object with changes made.
    """

    def __init__(self, *args, forced: bool = True, **kwargs):
        if forced:
            # If forced updates are enabled, we don't do any path validation.
            # Everything is mutable, nothing is forbidden
            self.operations = super(ArtifactPatch, self).operations
        else:
            self.operations = MappingProxyType(
                {
                    "remove": ArtifactRemoveOperation,
                    "add": ArtifactAddOperation,
                    "replace": ArtifactReplaceOperation,
                    "move": ArtifactMoveOperation,
                    "copy": ArtifactCopyOperation,
                }
            )

        super(ArtifactPatch, self).__init__(*args, **kwargs)

    def apply(self, obj: dict[str, JSON], in_place: bool = False) -> dict[str, JSON]:
        """
        Overwrites the behavior of apply to create a partially updated object
        (unless in_place is True). Since the API no longer relies on JSON schema, and
        serializers allow partial updates, we only need to return the fields which are
        updated. This makes serializer validation easier.

        The only limitation here is that the updates are resolved via a shallow diff.
        Deep diff would be ideal, but that is much more complicated. For now, this is
        ok since the nested objects are ok to be replaced completely. If database
        relationships ever get more complicated than they currently are, this will
        need to be updated.
        """
        try:
            new_artifact = super(ArtifactPatch, self).apply(obj, in_place=in_place)
        except jsonpatch.JsonPatchException as e:
            raise ValidationError(str(e))
        if errors := patch_errors.pop(id(self), None):
            raise ValidationError(errors)

        if in_place:
            return new_artifact

        updated_fields = {
            field: new_value
            for field, value in obj.items()
            if (new_value := new_artifact.get(field)) != value
        }

        return updated_fields

    def _get_operation(self, operation: JSONObject) -> jsonpatch.PatchOperation:
        """
        This override associates an ID with each operation object so that the
        owner of the object is able to aggregate errors from all the operations
        it owns.
        """
        try:
            op = super(ArtifactPatch, self)._get_operation(operation)
        except jsonpatch.InvalidJsonPatch as e:
            raise ValidationError(str(e))
        op.error_id = id(self)
        return op

"""
The classes in this file provide overrides to JSON Patch classes to ensure that
patches are valid specifically for our Trovi models.
"""
from collections import defaultdict
from functools import partial
from types import MappingProxyType
from typing import Any

import jsonpatch
from rest_framework.exceptions import ValidationError

from trovi.models import ArtifactAuthor
from util.types import JSONObject

patch_errors = defaultdict(list)


class ArtifactPatchMixin:
    """
    Provides helpers to all ArtifactPatchOperations
    """

    error_id = None
    INVALID_PATH = "I'm an invalid path because paths are only ever dict or None"
    _artifact_author_description = {
        str(f): None for f in ArtifactAuthor._meta.get_fields()
    }

    def _int_key_only(self, value: Any, desired_key: Any) -> Any:
        """
        Helper function that ensures a defaultdict's key is only an integer.
        User for paths that are supposed to be lists.
        """
        if type(desired_key) is not int:
            return self.INVALID_PATH
        else:
            return value

    _tag_key_generator = partial(_int_key_only, value=None)
    _author_key_generator = partial(_int_key_only, value=_artifact_author_description)
    _linked_project_generator = partial(_int_key_only, value=None)

    def valid_mutable_path(self, operation: dict, path: list):
        """
        Walks a path to determine if it is valid for a mutable operation
        """
        # Describes paths within an Artifact obj that are allowed to be modified.
        # All valid paths will be handled by the JSON Patch library itself,
        # since invalid paths will not appear in the object.
        walk = {
            "title": None,
            "short_description": None,
            "long_description": None,
            "tags": defaultdict(self._tag_key_generator),
            "authors": defaultdict(self._author_key_generator),
            "linked_projects": defaultdict(self._linked_project_generator),
            "reproducibility": {"enable_requests": None, "access_hours": None},
            # owner_urn is mutable, but only current owners can modify it
            # this is enforced by the ArtifactSerializer
            "owner_urn": None,
            "visibility": None,
        }
        for step in path:
            walk = walk.get(step, self.INVALID_PATH)
            if walk == self.INVALID_PATH:
                patch_errors[self.error_id].append(
                    f"Write operation '{operation['op']}' "
                    f"does not have valid mutable path: {path}"
                )
                return False
        return True


class ArtifactRemoveOperation(jsonpatch.RemoveOperation, ArtifactPatchMixin):
    def apply(self, obj: JSONObject) -> JSONObject:
        if self.pointer.parts != ["sharing_key"]:
            if not self.valid_mutable_path(self.operation, self.pointer.parts):
                return obj
        return super(ArtifactRemoveOperation, self).apply(obj)


class ArtifactAddOperation(jsonpatch.AddOperation, ArtifactPatchMixin):
    def apply(self, obj: JSONObject) -> JSONObject:
        if not self.valid_mutable_path(self.operation, self.pointer.parts):
            return obj
        return super(ArtifactAddOperation, self).apply(obj)


class ArtifactReplaceOperation(jsonpatch.ReplaceOperation, ArtifactPatchMixin):
    def apply(self, obj: JSONObject) -> JSONObject:
        if not self.valid_mutable_path(self.operation, self.pointer.parts):
            return obj
        return super(ArtifactReplaceOperation, self).apply(obj)


class ArtifactMoveOperation(jsonpatch.MoveOperation, ArtifactPatchMixin):
    def apply(self, obj: JSONObject) -> JSONObject:
        if not self.valid_mutable_path(self.operation, self.pointer.parts):
            return obj
        from_path = self.operation.get("from")
        if from_path:
            from_ptr = self.pointer_cls(from_path)
            if not self.valid_mutable_path(self.operation, from_ptr.parts):
                return obj
        return super(ArtifactMoveOperation, self).apply(obj)


class ArtifactCopyOperation(jsonpatch.CopyOperation, ArtifactPatchMixin):
    def apply(self, obj: JSONObject) -> JSONObject:
        if not self.valid_mutable_path(self.operation, self.pointer.parts):
            return obj
        return super(ArtifactCopyOperation, self).apply(obj)


class ArtifactPatch(jsonpatch.JsonPatch):

    operations = MappingProxyType(
        {
            "remove": ArtifactRemoveOperation,
            "add": ArtifactAddOperation,
            "replace": ArtifactReplaceOperation,
            "move": ArtifactMoveOperation,
            "copy": ArtifactCopyOperation,
        }
    )

    def apply(self, obj: JSONObject, in_place: bool = False) -> JSONObject:
        try:
            finished = super(ArtifactPatch, self).apply(obj, in_place=in_place)
        except Exception as e:
            raise ValidationError(str(e))
        if errors := patch_errors.pop(id(self), None):
            raise ValidationError(errors)
        return finished

    def _get_operation(self, operation: JSONObject) -> jsonpatch.PatchOperation:
        try:
            op = super(ArtifactPatch, self)._get_operation(operation)
        except jsonpatch.InvalidJsonPatch as e:
            raise ValidationError(str(e))
        op.error_id = id(self)
        return op

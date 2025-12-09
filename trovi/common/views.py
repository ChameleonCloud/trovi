from functools import cache
from typing import Type, Any

from django.db import models
from rest_framework import viewsets, serializers, permissions
from rest_framework.request import Request

from trovi.common.permissions import TroviAdminPermission


class TroviAPIViewSet(viewsets.GenericViewSet):
    """
    Implements generic behavior useful to all API views
    """

    # Serializer used for handling JSON-patch requests
    patch_serializer_class: serializers.Serializer = None
    # These properties exist to make permissions for each action more idiomatic
    # and less branchy
    # Any permission classes in these lists will be appended to the base
    # permission_classes list when permissions are checked
    list_permission_classes: list[Type[permissions.BasePermission]] = []
    retrieve_permission_classes: list[Type[permissions.BasePermission]] = []
    create_permission_classes: list[Type[permissions.BasePermission]] = []
    update_permission_classes: list[Type[permissions.BasePermission]] = []
    destroy_permission_classes: list[Type[permissions.BasePermission]] = []

    def get_permissions(self) -> list[Type[permissions.BasePermission]]:
        action_permissions = []
        # TODO python3.10 pattern matching
        if self.action == "list":
            action_permissions = self.list_permission_classes
        elif self.action == "retrieve":
            action_permissions = self.retrieve_permission_classes
        elif self.action == "create":
            action_permissions = self.create_permission_classes
        elif self.action in ("update", "partial_update"):
            action_permissions = self.update_permission_classes
        elif self.action in ("destroy", "unassign"):
            action_permissions = self.destroy_permission_classes
        return super(TroviAPIViewSet, self).get_permissions() + [
            permission() for permission in action_permissions
        ]

    def check_permissions(self, request: Request):
        """
        Adds permission overrides for Trovi service admins, as they're allowed to do
        everything
        """
        if not TroviAdminPermission().has_permission(request, self):
            super(TroviAPIViewSet, self).check_permissions(request)

    def check_object_permissions(self, request: Request, obj: Any):
        """
        Adds permission overrides for Trovi service admins, as they're allowed to do
        everything
        """
        if not TroviAdminPermission().has_object_permission(request, self, obj):
            super(TroviAPIViewSet, self).check_object_permissions(request, obj)

    @cache
    def get_object(self) -> models.Model:
        # This override caches ``get`` queries so the same object
        # can be referenced in multiple functions without redundant database round-trips
        return super(TroviAPIViewSet, self).get_object()

    def get_queryset(self) -> models.QuerySet:
        # This override ensures relevant objects in the database to maintain the same
        # state for any operations which require that behavior.
        qs = super(TroviAPIViewSet, self).get_queryset()

        # Only use select_for_update for actual modifications.
        # "list" and "create" should NOT lock rows.
        if self.action.lower() in ("update", "partial_update"):
            qs = qs.select_for_update()
        return qs

    def get_serializer_class(self):
        if self.is_patch():
            return self.patch_serializer_class
        else:
            return super(TroviAPIViewSet, self).get_serializer_class()

    def is_patch(self) -> bool:
        return self.request.method.upper() in ("PATCH", "PUT")

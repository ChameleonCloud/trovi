from django.db import models
from django.db.models import Sum
from rest_framework import filters, views
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request


class ListArtifactsOrderingFilter(filters.OrderingFilter):
    """
    Handles sorting for ListArtifacts
    """

    def filter_queryset(
        self, request: Request, queryset: models.QuerySet, view: views.View
    ) -> models.QuerySet:
        sort_by = request.query_params.get("sort_by")

        if sort_by is not None:
            if sort_by == "date":
                query = queryset.order_by("created_at")
            elif sort_by == "access_count":
                query = queryset.annotate(
                    access_count=Sum("versions__access_count")
                ).order_by("-access_count")
            else:
                raise ValidationError(
                    f"ListArtifact: Unknown 'sort_by' key. ({sort_by})"
                )
        else:
            # By default, artifacts are sorted by UUID
            query = queryset.order_by("uuid")

        return query

from django.db import models
from django.db.models import Sum
from rest_framework import filters, views
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request

from trovi.common.tokens import JWT
from trovi.models import Artifact


class ListArtifactsOrderingFilter(filters.OrderingFilter):
    """
    Handles sorting for ListArtifacts
    """

    def filter_queryset(
        self, request: Request, queryset: models.QuerySet, view: views.View
    ) -> models.QuerySet:
        sharing_key = request.query_params.get("sharing_key")
        token = JWT.from_request(request)

        if token.is_admin():
            return queryset

        if token:
            user = token.azp
        else:
            user = None

        public = queryset.filter(visibility=Artifact.Visibility.PUBLIC)
        private = queryset.filter(visibility=Artifact.Visibility.PRIVATE)
        if sharing_key:
            shared_with = private.filter(sharing_key=sharing_key)
        else:
            shared_with = Artifact.objects.none()
        member_of = private.filter(authors__email__iexact=user)

        authz_query = (public | shared_with | member_of).distinct()

        sort_by = request.query_params.get("sort_by")

        if sort_by is not None:
            if sort_by == "date":
                sorted_query = authz_query.order_by("created_at")
            elif sort_by == "access_count":
                sorted_query = authz_query.annotate(
                    access_count=Sum("versions__access_count")
                ).order_by("-access_count")
            else:
                raise ValidationError(f"Unknown 'sort_by' key. ({sort_by})")
        else:
            # By default, artifacts are sorted by most recently updated
            sorted_query = authz_query.order_by("-updated_at")

        return sorted_query

from django.db import models
from django.db.models import F
from django.utils.translation import gettext_lazy as _
from rest_framework import filters, views
from rest_framework.request import Request

from trovi.common.tokens import JWT
from trovi.models import Artifact


class ListArtifactsOrderingFilter(filters.OrderingFilter):
    """
    Handles sorting for ListArtifacts
    """

    ordering_param = "sort_by"
    ordering_fields = ["date", "access_count", "updated_at"]
    ordering_description = _("The criteria by which to sort the Artifacts.")

    def filter_queryset(
        self, request: Request, queryset: models.QuerySet, view: views.View
    ) -> models.QuerySet:

        # Annotate the query such that the database understands our sort_by params
        prepared_query = queryset.annotate(date=F("created_at"))

        # The prepared query from above will be sorted properly using the
        # sort_by url param in the super call here
        return (
            super(ListArtifactsOrderingFilter, self)
            .filter_queryset(request, prepared_query, view)
            .reverse()
        )


class ListArtifactsVisibilityFilter(filters.BaseFilterBackend):
    """
    Filters the queryset for Artifacts that the user has permission to see
    """

    def filter_queryset(
        self, request: Request, queryset: models.QuerySet, view: views.View
    ) -> models.QuerySet:
        # TODO support multiple sharing keys
        sharing_key = request.query_params.get("sharing_key")
        token = JWT.from_request(request)

        if token.is_admin():
            return queryset

        if token:
            user = token.sub
        else:
            user = None

        public = queryset.filter(visibility=Artifact.Visibility.PUBLIC)
        private = queryset.filter(visibility=Artifact.Visibility.PRIVATE)

        if sharing_key:
            shared_with = private.filter(sharing_key=sharing_key)
        else:
            shared_with = Artifact.objects.none()
        member_of = private.filter(authors__email__iexact=user)

        return (public | shared_with | member_of).distinct()

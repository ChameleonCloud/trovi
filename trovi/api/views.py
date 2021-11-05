from uuid import uuid4

from django import views
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.db import transaction
from django.db.models import Sum
from django.http import JsonResponse, HttpRequest

from trovi.api.responses import (
    JsonNotFoundResponse,
    JsonServerErrorResponse,
    JsonBadRequestResponse,
)
from trovi.models import Artifact


class ListArtifacts(views.View):
    """
    Implements ListArtifact API endpoint.
    Lists all the user's Artifacts and relevant metadata

    TODO auth
    """

    @staticmethod
    @transaction.atomic
    def get(request: HttpRequest) -> JsonResponse:
        """
        /artifacts[?after=<cursor>&limit=<limit>&sort_by=<field>]

        Lists all visible artifacts for the requesting user.

        The optional "after" parameter enables pagination; it marks
        the starting point for the response.

        The optional "limit" parameter dictates how many artifacts should be returned
        in the response

        The list can be sorted by "date" or by any of the "metrics" counters.
        """
        after = request.GET.get("after")
        limit = request.GET.get("limit")
        sort_by = request.GET.get("sort_by")

        query = Artifact.objects.all()

        if after is not None:
            try:
                begin = Artifact.objects.get(uuid=after)
            except ObjectDoesNotExist:
                return JsonBadRequestResponse(
                    f"ListArtifacts: Unknown artifact in 'after' parameter. ({after})"
                )
        else:
            begin = None

        # Sorting is done first to ensure consistency with
        # Pagination is done in-band with sorting,
        # as this is the easiest way to create the correct slice of artifacts
        if sort_by is not None:
            if sort_by == "date":
                query = query.order_by("created_at")
                if begin:
                    query = query.filter(created_at__gte=begin.created_at)
            elif sort_by == "access_count":
                query = query.annotate(
                    access_count=Sum("versions__access_count")
                ).order_by("-access_count")
                if begin:
                    query = query.filter(
                        access_count__gte=sum(v.access_count for v in begin.versions)
                    )
            else:
                return JsonBadRequestResponse(
                    f"ListArtifact: Unknown 'sort_by' key. ({sort_by})"
                )
        else:
            # By default, artifacts are sorted by UUID
            query = query.order_by("uuid")
            if begin:
                query = query.filter(uuid__gte=begin.uuid)

        if limit is not None:
            try:
                max_artifacts = int(limit)
            except ValueError:
                return JsonBadRequestResponse(
                    f"ListArtifacts: 'limit' must be an integer. ({limit})"
                )
            end = min(max_artifacts, query.count())
        else:
            end = query.count()

        artifacts = [artifact.to_json() for artifact in query[:end]]
        next_after = artifacts[0]["id"] if len(artifacts) > 0 else None

        result = {
            "artifacts": artifacts,
            "next": {"after": next_after, "limit": end},
        }
        return JsonResponse(result)


class GetArtifact(views.View):
    """
    Implements the GetArtifact API endpoint.
    Gets a user's Artifact by UUID.

    TODO auth
    """

    @staticmethod
    def get(request: HttpRequest, artifact_uuid: uuid4) -> JsonResponse:
        """
        Gets an artifact model by its UUID (primary key)
        and returns its JSON representation
        """
        try:
            artifact = Artifact.objects.get(uuid=artifact_uuid)
        except ObjectDoesNotExist:
            return JsonNotFoundResponse(f"Artifact {artifact_uuid} not found.")
        except MultipleObjectsReturned:
            return JsonServerErrorResponse(
                f"UUID {artifact_uuid} associated with multiple artifacts.",
            )
        return JsonResponse(artifact.to_json())

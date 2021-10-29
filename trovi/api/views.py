from django import views
from django.http import JsonResponse
from uuid import uuid4

from trovi.api.responses import JsonNotFoundResponse, JsonServerErrorResponse
from trovi.models import Artifact


class ListArtifact(views.View):
    """
    Implements ListArtifact API endpoint.
    Lists all the user's Artifacts and relevant metadata

    TODO auth
    """

    @staticmethod
    def get(request) -> JsonResponse:
        """
        Serializes all of the user's Artifacts to JSON
        """
        artifacts = {
            "artifacts": [artifact.to_json() for artifact in Artifact.objects.all()]
        }
        return JsonResponse(artifacts)


class GetArtifact(views.View):
    """
    Implements the GetArtifact API endpoint.
    Gets a user's Artifact by UUID.

    TODO auth
    """

    @staticmethod
    def get(request, artifact_uuid: uuid4) -> JsonResponse:
        """
        Gets an artifact model by its UUID (primary key)
        and returns its JSON representation
        """
        try:
            artifact = Artifact.objects.get(uuid=artifact_uuid)
        except Artifact.module.DoesNotExist:
            return JsonNotFoundResponse(f"Artifact {artifact_uuid} not found.")
        except Artifact.module.MultipleObjectsReturned:
            return JsonServerErrorResponse(
                f"UUID {artifact_uuid} associated with multiple artifacts.",
            )
        return JsonResponse(artifact.to_json())

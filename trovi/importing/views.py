from django.conf import settings
from django.db import transaction
from rest_framework import mixins
from trovi.api.serializers import ArtifactPatchSerializer, ArtifactSerializer, ArtifactVersionSerializer
from trovi.common.authenticators import TroviTokenAuthentication
from trovi.common.permissions import ArtifactEditPermission, ArtifactReadScopePermission, ArtifactViewPermission, ArtifactWriteScopePermission
from trovi.common.serializers import get_requesting_user_urn, get_user_urn_from_request
from trovi.common.views import TroviAPIViewSet
from trovi.importing.serializers import ArtifactImportSerializer
from rest_framework.response import Response
from rest_framework import viewsets
from rest_framework import exceptions as drf_exceptions
from giturlparse import parse
from github import Github, GithubException, Auth

from rocrate.rocrate import ROCrate
from rocrate.model.metadata import Metadata

import jsonpatch
import tempfile
import base64

import logging

from trovi.models import Artifact, ArtifactTag, ArtifactVersion

LOG = logging.getLogger(__name__)

# Overwrite the ro-crate filename
Metadata.BASENAME = settings.RO_CRATE_FILENAME

class ArtifactImportView(TroviAPIViewSet):
    serializer_class = ArtifactImportSerializer
    authentication_classes = [TroviTokenAuthentication]
    create_permission_classes = [ArtifactWriteScopePermission]
    update_permission_classes = [
        ArtifactReadScopePermission,
        ArtifactWriteScopePermission,
        ArtifactViewPermission,
        ArtifactEditPermission,
    ]

    def _parse_git_url(self, url, request):
        """
        Parses a git URL into artifact data

        Raises ValidationError if issue occurs.
        """
        parsed_git_url = parse(url)
        if not(parsed_git_url and parsed_git_url.host == "github.com"):
            raise drf_exceptions.ValidationError(
                "Importing artifact metadata is only supported from github.com")

        with Github(
            login_or_token=settings.GITHUB_ACCESS_TOKEN,
        ) as g:
            repo_name = f"{parsed_git_url.owner}/{parsed_git_url.repo}"
            repo = g.get_repo(repo_name)
            
            artifact_data = {}
            # We could import many things from github here in the future.
            git_version = repo.get_commits()[0].sha
            remote_url = next(
                remote for proto, remote in parsed_git_url.urls.items() if proto == "https")
            trovi_urn = f"urn:trovi:contents:git:{remote_url}@{git_version}"
            artifact_data["version"] = {
                "contents": {"urn": trovi_urn},
                "environment_setup": [],
            }
            artifact_data["authors"] = []
            artifact_data["tags"] = []
            
            try:
                # Save the github file to a temp file
                contents = repo.get_contents(settings.RO_CRATE_FILENAME)
                content = base64.b64decode(contents.content).decode("utf-8")
                with tempfile.TemporaryDirectory() as temp_dir:
                    with open(f"{temp_dir}/{settings.RO_CRATE_FILENAME}", "w") as f:
                        f.write(content)

                    # Load metadata from crate
                    crate = ROCrate(temp_dir)
                    crate = crate.dereference("./")
                    artifact_data["title"] = crate.get("name")
                    artifact_data["short_description"] = crate.get("disambiguatingDescription")
                    artifact_data["long_description"] = crate.get("description")
                    artifact_data["owner_urn"] = get_user_urn_from_request(request)
                    for t in crate.get("keywords").split(","):
                        artifact_data["tags"].append(t.strip())

                    for a in crate.get("author"):
                        artifact_data["authors"].append(
                            {
                                "full_name": a.get("name"),
                                "email": a.get("email"),
                                "affiliation": a.get("affiliation"),
                            }
                        )

                    for obj in crate.get("actionApplication", []):
                        if obj.type == "SoftwareApplication" and obj.get("trovi_type"):
                            artifact_data["version"]["environment_setup"].append({
                                "type": obj.get("trovi_type"),
                                "arguments": obj.get("trovi_arguments"),
                            })
                    return artifact_data
            except GithubException:
                raise drf_exceptions.ValidationError("Could not fetch information from GitHub.")

    @transaction.atomic
    def update(self, request, pk):
        old_instance = Artifact.objects.get(pk=pk)
        old_artifact = ArtifactSerializer(
            old_instance,
            context={
                "request": request,
                "view": self,
            }
        )
        d = ArtifactImportSerializer(data=request.data)
        if d.is_valid():
            artifact_data = self._parse_git_url(
                d.validated_data.get("github_url"), request
            )
            # _parse_git_url assumes singular version, move it to a list
            v = artifact_data.pop("version")
            js_patch = jsonpatch.JsonPatch.from_diff(old_artifact.data, artifact_data)
            patch = [
                d for d in js_patch
                if d["op"] != "remove" # filter out readonly fields
            ]
            patch_serializer = ArtifactPatchSerializer(
                old_instance, 
                data={"patch": patch},
                context={
                    "request": request,
                    "view": self,
                },
            )
            patch_serializer.is_valid(raise_exception=True)
            updated_artifact = patch_serializer.save()
            version_serializer = ArtifactVersionSerializer(data=v, context={
                "request": request,
                "view": self,
            })
            version_serializer.is_valid(raise_exception=True)
            version = version_serializer.save()
            # Set the artifact, which can't be done via the serializer
            version.artifact = updated_artifact
            version.save()
            # Pretend we just created this artifact. Otherwise the
            # slug won't get increment right.
            ArtifactVersion.generate_slug(version, created=True)
            return Response(patch_serializer.data)
        return Response(d.errors)


    @transaction.atomic
    def create(self, request):
        d = ArtifactImportSerializer(data=request.data)
        if d.is_valid():
            artifact_data = self._parse_git_url(
                d.validated_data.get("github_url"), request
            )
            artifact_serializer = ArtifactSerializer(data=artifact_data, context={
                "request": request,
                "view": self,
            })
            if not artifact_serializer.is_valid():
                return Response(artifact_serializer.errors)
            artifact_serializer.save()
            return Response(artifact_serializer.data)
        return Response(d.errors)

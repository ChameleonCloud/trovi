from rest_framework_extensions import routers

from trovi.api.views import ArtifactViewSet, ArtifactVersionViewSet

router = routers.ExtendedSimpleRouter()

router.register("", ArtifactViewSet).register(
    "versions",
    ArtifactVersionViewSet,
    basename="artifact-version",
    parents_query_lookups=["artifact"],
)

urlpatterns = router.get_urls()

# Because of how Django URL configuration works, we can't have multiple views at the
# same path. So, in order to facilitate reverse lookups, we use these variables to
# avoid the confusing naming pattern required for the ViewSet to include multiple
# views at the same path.
ListArtifact = "artifact-list"
GetArtifact = "artifact-detail"
CreateArtifact = "artifact-list"
UpdateArtifact = "artifact-detail"

CreateArtifactVersion = "artifact-version-list"
DeleteArtifactVersion = "artifact-version-detail"

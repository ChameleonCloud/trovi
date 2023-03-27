from trovi.api.views import (
    ArtifactViewSet,
    ArtifactVersionViewSet,
    MigrateArtifactVersionViewSet,
    ArtifactRoleViewSet,
)
from trovi.common.routers import TroviRouter

router = TroviRouter()

router.register("", ArtifactViewSet).register(
    "versions",
    ArtifactVersionViewSet,
    basename="artifact-version",
    parents_query_lookups=["artifact"],
).register(
    "migration",
    MigrateArtifactVersionViewSet,
    basename="migrate-artifact-version",
    parents_query_lookups=["artifact", "version"],
)

router.register("", ArtifactViewSet).register(
    "roles",
    ArtifactRoleViewSet,
    basename="artifact-role",
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
IncrArtifactVersionMetrics = "artifact-version-metrics"

MigrateArtifactVersion = "migrate-artifact-version-list"

AssignArtifactRole = "artifact-role-list"
UnassignArtifactRole = "artifact-role-list"
ListArtifactRole = "artifact-role-list"

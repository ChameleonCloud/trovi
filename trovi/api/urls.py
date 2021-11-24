from rest_framework import routers

from trovi.api.views import ArtifactViewSet

router = routers.SimpleRouter()

router.register("", ArtifactViewSet)

urlpatterns = router.get_urls()

# Because of how Django URL configuration works, we can't have multiple views at the
# same path. So, in order to facilitate reverse lookups, we use these variables to
# avoid the confusing naming pattern required for the ViewSet to include multiple
# views at the same path.
ListArtifact = "artifact-list"
GetArtifact = "artifact-detail"
CreateArtifact = "artifact-list"
UpdateArtifact = "artifact-detail"

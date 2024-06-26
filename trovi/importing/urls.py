from django.urls import re_path

from trovi.importing import views

from rest_framework.routers import SimpleRouter

router = SimpleRouter()
router.register("", views.ArtifactImportView, basename="import")

urlpatterns = router.urls
from django.urls import path

import api.views

urlpatterns = [
    path("", api.views.ListArtifact.as_view()),
    path("<uuid:artifact_uuid>", api.views.GetArtifact.as_view()),
]

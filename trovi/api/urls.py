from django.urls import path

from trovi.api import views

urlpatterns = [
    path("", views.ListArtifacts.as_view(), name="ListArtifacts"),
    path("<uuid:artifact_uuid>", views.GetArtifact.as_view(), name="GetArtifact"),
]

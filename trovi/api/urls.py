from django.urls import path

from trovi.api import views

urlpatterns = [
    path("", views.ListArtifact.as_view()),
    path("<uuid:artifact_uuid>", views.GetArtifact.as_view()),
]

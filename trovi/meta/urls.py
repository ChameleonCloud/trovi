from django.urls import path

from trovi.meta import views

urlpatterns = [
    path(
        "tags/",
        views.ArtifactTagsView.as_view({"get": "list", "post": "create"}),
        name="Tags",
    ),
]

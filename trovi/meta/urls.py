from django.urls import re_path

from trovi.meta import views

urlpatterns = [
    re_path(
        "^tags/?",
        views.ArtifactTagsView.as_view({"get": "list", "post": "create"}),
        name="Tags",
    ),
]

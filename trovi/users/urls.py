from django.urls import re_path

from trovi.users import views

urlpatterns = [
    re_path(
        "^me/?",
        views.UserProfileView.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="UserProfile",
    ),
]

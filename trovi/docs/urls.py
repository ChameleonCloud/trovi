from django.urls import path
from drf_spectacular import views
from rest_framework.permissions import AllowAny

urlpatterns = [
    path(
        "schema/",
        views.SpectacularJSONAPIView.as_view(
            authentication_classes=[],
            permission_classes=[AllowAny],
        ),
        name="schema",
    ),
    path(
        "swagger/",
        views.SpectacularSwaggerView.as_view(
            authentication_classes=[],
            permission_classes=[AllowAny],
        ),
        name="swagger",
    ),
]

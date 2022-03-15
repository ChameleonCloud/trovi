from django.urls import path
from drf_spectacular import views

urlpatterns = [
    path("schema/", views.SpectacularJSONAPIView.as_view(), name="SchemaDocumentation"),
    path(
        "swagger/",
        views.SpectacularSwaggerView.as_view(url_name="SchemaDocumentation"),
        name="SwaggerDocumentation",
    ),
]

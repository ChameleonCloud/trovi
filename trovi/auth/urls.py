from django.urls import path

from trovi.auth import views

urlpatterns = [
    path("", views.TokenGrant.as_view(), name="TokenGrant"),
]

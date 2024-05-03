"""trovi URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include, re_path

urlpatterns = [
    path("trovi-admin-portal/", admin.site.urls),
    re_path(r"^artifacts/?", include("trovi.api.urls")),
    re_path(r"^token/?", include("trovi.auth.urls")),
    re_path(r"^contents/?", include("trovi.storage.urls")),
    re_path(r"^docs/?", include("trovi.docs.urls")),
    re_path(r"^meta/?", include("trovi.meta.urls")),
]

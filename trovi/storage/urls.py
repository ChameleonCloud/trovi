from rest_framework import routers

from trovi.storage.views import StorageViewSet

router = routers.SimpleRouter()

router.register("", StorageViewSet, basename="contents")

urlpatterns = router.get_urls()

StoreContents = "contents-list"
RetrieveContents = "contents-list"

import sys

from django.apps import AppConfig
from django.db.models.signals import post_save, post_delete


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "trovi.api"

    def ready(self):
        # These have to be imported here to avoid circular dependencies
        from trovi.models import ArtifactEvent
        from trovi.api.serializers import _get_unique_event_count

        def _clear_cache(sender, instance: ArtifactEvent, **kwargs):
            """Clear cache when artifact events are created or deleted."""
            _get_unique_event_count.cache_clear()

        post_save.connect(_clear_cache, sender=ArtifactEvent)
        post_delete.connect(_clear_cache, sender=ArtifactEvent)

        # Register signal to trigger crawl request processing
        from trovi.models import CrawlRequest
        from trovi.celery.tasks import process_crawl_request

        def trigger_crawl_request(
            sender, instance: CrawlRequest, created: bool, **kwargs
        ):
            """Trigger a celery task to process the crawl request"""
            if created:
                process_crawl_request.delay(instance.id)

        post_save.connect(trigger_crawl_request, sender=CrawlRequest)

        # Only run if we're spinning up the server
        if "runserver" in sys.argv:
            from trovi.api.tasks import (
                reap_unfinished_migrations,
                requeue_queued_migrations,
            )

            reap_unfinished_migrations()
            requeue_queued_migrations()

import sys

from django.apps import AppConfig
from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "trovi.api"

    def ready(self):
        # These have to be imported here to avoid circular dependencies
        # Register signal to trigger crawl request processing
        from trovi.models import ArtifactComment, CrawlRequest
        from trovi.celery.tasks import process_crawl_request, send_comment_notification

        def trigger_crawl_request(
            sender, instance: CrawlRequest, created: bool, **kwargs
        ):
            """Trigger a celery task to process the crawl request"""
            if created:
                process_crawl_request.delay(instance.id)

        post_save.connect(trigger_crawl_request, sender=CrawlRequest, weak=False)

        def trigger_comment_notification(
            sender, instance: ArtifactComment, created: bool, **kwargs
        ):
            """Queue notification emails once the new comment is committed"""
            if created and settings.TROVI_COMMENT_NOTIFICATIONS_ENABLED:
                transaction.on_commit(
                    lambda: send_comment_notification.delay(instance.pk), robust=True
                )

        post_save.connect(
            trigger_comment_notification, sender=ArtifactComment, weak=False
        )

        # Only run if we're spinning up the server
        if "runserver" in sys.argv:
            from trovi.api.tasks import (
                reap_unfinished_migrations,
                requeue_queued_migrations,
            )

            reap_unfinished_migrations()
            requeue_queued_migrations()

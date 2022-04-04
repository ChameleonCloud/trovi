import sys

from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "trovi.api"

    def ready(self):
        # Only run if we're spinning up the server
        if "runserver" in sys.argv:
            from trovi.api.tasks import (
                reap_unfinished_migrations,
                requeue_queued_migrations,
            )

            reap_unfinished_migrations()
            requeue_queued_migrations()

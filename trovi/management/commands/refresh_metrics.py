from django.core.management.base import BaseCommand

from trovi.metrics import refresh_metrics


class Command(BaseCommand):
    help = (
        "Recompute every artifact and version metric from the event log. "
        "Prints how many rows changed, which is 0 when none had drifted."
    )

    def handle(self, *args, **options):
        self.stdout.write(f"Refreshed metrics: {refresh_metrics()} row(s) changed")

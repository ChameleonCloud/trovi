import logging
from concurrent.futures import ThreadPoolExecutor
from inspect import Traceback
from typing import Type

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from trovi.models import ArtifactVersionMigration
from trovi.storage.backends import get_backend

LOG = logging.getLogger(__name__)

artifact_version_migration_executor = ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="trovi-migrate-version"
)


class ArtifactVersionMigrationErrorHandler:
    """
    Simple context manager for handling possibly unexpected errors with
    migrations, so they don't get stuck forever
    """

    def __init__(self, migration: ArtifactVersionMigration):

        self.migration = migration

    def __enter__(self):
        with transaction.atomic():
            self.migration.status = ArtifactVersionMigration.MigrationStatus.IN_PROGRESS
            self.migration.message = "Selected for migration"
            self.migration.save()

        return self

    def __exit__(
        self, exc_type: Type[Exception], exc_val: Exception, exc_tb: Traceback
    ):
        if not exc_val:
            return

        version = self.migration.artifact_version
        LOG.exception(
            f"Uncaught error migrating artifact version "
            f"{version.artifact.uuid}/{version.slug}"
        )

        self.handle_error("Unknown error occurred")

    def handle_error(self, message: str):
        with transaction.atomic():
            self.migration.status = ArtifactVersionMigration.MigrationStatus.ERROR
            self.migration.message = message
            self.migration.save(update_fields=["status", "message"])


def migrate_artifact_version(migration: ArtifactVersionMigration):
    """
    Performs the task of migrating an artifact version to a different backend.
    """

    migration_status = ArtifactVersionMigration.MigrationStatus
    dest_backend_name = migration.backend
    source = migration.source_urn
    # urn:trovi:contents:<backend>:<id>
    source_backend_name, source_id = source.split(":")[3:5]
    source_backend = get_backend(
        source_backend_name, content_id=source_id, version=migration.artifact_version
    )
    dest_backend = get_backend(dest_backend_name, version=migration.artifact_version)
    with ArtifactVersionMigrationErrorHandler(migration) as error_handler:
        with source_backend:
            n_bytes = len(dest_backend)
            if n_bytes < 1:
                error_handler.handle_error("Empty source cannot be migrated.")
                return

            with transaction.atomic():
                migration.message = f"Uploading to {dest_backend.name}"
                migration.started_at = timezone.now()
                migration.save()
            bytes_written = 0

            while source_backend.readable():
                try:
                    chunk = source_backend.read(settings.FILE_UPLOAD_MAX_MEMORY_SIZE)
                except IOError:
                    error_handler.handle_error(f"Error reading from source")
                    return

                try:
                    write_size = dest_backend.write(chunk)
                except IOError:
                    error_handler.handle_error("Error writing to destination")
                    return

                bytes_written += write_size
                with transaction.atomic():
                    migration.message_ratio = bytes_written / n_bytes
                    migration.save()

        # Migration has finished
        with transaction.atomic():
            migration.status = migration_status.SUCCESS
            migration.message = f"Uploaded to {dest_backend.to_urn()}"
            migration.message_ratio = 1.0
            migration.finished_at = timezone.now()
            migration.destination_urn = dest_backend.to_urn()
            migration.save()
        source_backend.seek(0)


# The functions below handle events that could not execute properly due to a
# shutdown. Migrations that were started, but could not finish, result in an error,
# as restarting them might result in corruption. This should only happen in
# extraordinary circumstances, such as power failure, as the default behavior of the
# executor is to wait on unfinished threads when it receives an interrupt.
#
# Queued migrations are thrown back into  the task queue, as they have not started yet.


def reap_unfinished_migrations():

    in_progress = ArtifactVersionMigration.objects.filter(
        status=ArtifactVersionMigration.MigrationStatus.IN_PROGRESS
    )

    LOG.info(
        f"Found {in_progress.count()} artifact migration(s) interrupted by shutdown."
    )

    in_progress.update(
        status=ArtifactVersionMigration.MigrationStatus.ERROR,
        message="Migration was interrupted by an internal server error",
    )


def requeue_queued_migrations():
    queued = ArtifactVersionMigration.objects.filter(
        status=ArtifactVersionMigration.MigrationStatus.QUEUED
    )

    LOG.info(f"Re-Queueing {queued.count()} artifact migration(s).")

    artifact_version_migration_executor.map(migrate_artifact_version, queued)

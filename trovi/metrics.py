"""
Artifact and version metrics, precomputed from the event log.

Each metric is declared once in METRICS, in API output order. It is stored at every
level whose metrics table has a column with its name. Adding a metric takes an entry
here and a column migration. A column named "<metric>_baseline" holds counts no longer
in the event log, which are added to that metric.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, Union
from uuid import UUID

from django.conf import settings
from django.db import models, transaction
from django.db.models import Count, Q
from django.utils import timezone

from trovi.models import ArtifactEvent, ArtifactMetrics, ArtifactVersionMetrics

EventType = ArtifactEvent.EventType
VERIFICATIONS = (EventType.VERIFY, EventType.VERIFY_FAILED)


@dataclass(frozen=True)
class Metric:
    name: str
    counts: EventType
    distinct_users: bool = False
    # Only counts events from the last ARTIFACT_RECENT_METRICS_DAYS
    recent: bool = False

    @property
    def latest_only(self) -> bool:
        # Users may change their verification answer, and only their latest counts
        return self.counts in VERIFICATIONS

    @property
    def fed_by(self) -> tuple[EventType, ...]:
        # A new answer can retract a user's previous one, of either type
        return VERIFICATIONS if self.latest_only else (self.counts,)

    def aggregate(self) -> Count:
        q = Q(event_type=self.counts)
        if self.recent:
            days = settings.ARTIFACT_RECENT_METRICS_DAYS
            q &= Q(timestamp__gte=timezone.now() - timezone.timedelta(days=days))
        if self.distinct_users:
            return Count("event_origin", distinct=True, filter=q)
        return Count("pk", filter=q)


METRICS = (
    Metric("access_count", EventType.LAUNCH),
    Metric("unique_access_count", EventType.LAUNCH, distinct_users=True),
    Metric(
        "unique_cell_execution_count", EventType.CELL_EXECUTION, distinct_users=True
    ),
    Metric("recent_access_count", EventType.LAUNCH, recent=True),
    Metric(
        "recent_unique_access_count", EventType.LAUNCH, distinct_users=True, recent=True
    ),
    Metric("verified_count", EventType.VERIFY, distinct_users=True),
    Metric("verify_failed_count", EventType.VERIFY_FAILED, distinct_users=True),
)
ARTIFACT_METRICS = tuple(m for m in METRICS if hasattr(ArtifactMetrics, m.name))
VERSION_METRICS = tuple(m for m in METRICS if hasattr(ArtifactVersionMetrics, m.name))


def refresh_metrics(
    artifact_id: Optional[UUID] = None,
    version_id: Optional[int] = None,
    event_types: Optional[Iterable[EventType]] = None,
) -> int:
    """
    Recomputes stored metrics from the event log, and returns how many rows changed.
    Refreshes every artifact and version, unless given an artifact. Then only that
    artifact and the given version are refreshed. With event_types, only the metrics
    they feed are recomputed.
    """
    # One transaction, so the row locks are held until the new counts are written
    with transaction.atomic():
        changed = _refresh_table(
            ArtifactMetrics,
            ARTIFACT_METRICS,
            event_field="artifact",
            pk=artifact_id,
            event_types=event_types,
        )

        # Scoped to an artifact without a version, so the versions are left
        # alone rather than all refreshed
        refresh_versions = artifact_id is None or version_id is not None
        if refresh_versions:
            changed += _refresh_table(
                ArtifactVersionMetrics,
                VERSION_METRICS,
                event_field="artifact_version",
                pk=version_id,
                event_types=event_types,
            )

    return changed


def _refresh_table(
    table: type[models.Model],
    metrics: Sequence[Metric],
    event_field: str,
    pk: Optional[Union[UUID, int]],
    event_types: Optional[Iterable[EventType]],
) -> int:
    """
    Recomputes the metrics stored in table, for every row or only the row with pk,
    and returns how many rows changed. Each row belongs to an artifact or version,
    which events link to with event_field.
    """
    # The other metrics can't have changed, so aren't recounted
    if event_types:
        metrics = [
            metric
            for metric in metrics
            if any(event_type in event_types for event_type in metric.fed_by)
        ]

    rows = table.objects.select_for_update()
    if pk is not None:
        rows = rows.filter(pk=pk)
    rows = list(rows)

    counts = _count_events(metrics, event_field, pk)

    changed_rows = []
    for row in rows:
        row_counts = counts.get(row.pk, {})
        row_changed = False
        for metric in metrics:
            # Only some metrics have a baseline column
            baseline = getattr(row, f"{metric.name}_baseline", 0)
            new_value = row_counts.get(metric.name, 0) + baseline
            if getattr(row, metric.name) != new_value:
                setattr(row, metric.name, new_value)
                row_changed = True
        # Only changed rows are written, so a refresh which finds no drift
        # writes nothing and returns 0
        if row_changed:
            changed_rows.append(row)

    # Bounds the size of each UPDATE, which has a CASE over every row for
    # every column
    fields = [metric.name for metric in metrics]
    table.objects.bulk_update(changed_rows, fields, batch_size=500)

    return len(changed_rows)


def _count_events(
    metrics: Sequence[Metric], event_field: str, pk: Optional[Union[UUID, int]]
) -> dict:
    """
    Counts each metric for every artifact or version, or only the one with pk.
    Returns {pk: {metric name: count}}, leaving out those with nothing to count.
    """
    if pk is None:
        event_filter = {}
    else:
        event_filter = {event_field: pk}

    counts = defaultdict(dict)

    # Most metrics count every event of their type
    event_metrics = [metric for metric in metrics if not metric.latest_only]
    if event_metrics:
        events = ArtifactEvent.objects.filter(**event_filter)
        _add_counts(counts, events, event_metrics, event_field)

    # Verification metrics count only each user's latest answer
    verification_metrics = [metric for metric in metrics if metric.latest_only]
    if verification_metrics:
        latest_answers = ArtifactEvent.latest_verifications(**event_filter)
        _add_counts(counts, latest_answers, verification_metrics, event_field)

    return counts


def _add_counts(
    counts: dict,
    events: models.QuerySet,
    metrics: Sequence[Metric],
    event_field: str,
) -> None:
    """Counts each metric in events with one GROUP BY query, and adds them to counts"""
    event_types = [metric.counts for metric in metrics]
    aggregates = {metric.name: metric.aggregate() for metric in metrics}
    # Calling values() before annotate() groups by event_field
    rows = (
        events.filter(event_type__in=event_types)
        .values(event_field)
        .annotate(**aggregates)
    )
    for row in rows:
        object_counts = counts[row[event_field]]
        for metric in metrics:
            object_counts[metric.name] = row[metric.name]

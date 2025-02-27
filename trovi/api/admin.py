from django.contrib import admin
from ..models import (
    Artifact,
    ArtifactVersion,
    ArtifactVersionMigration,
    ArtifactEvent,
    ArtifactTag,
    ArtifactAuthor,
    ArtifactProject,
    ArtifactLink,
    ArtifactRole,
)


@admin.register(Artifact)
class ArtifactAdmin(admin.ModelAdmin):
    list_display = (
        "uuid",
        "title",
        "visibility",
        "created_at",
        "updated_at",
        "owner_urn",
    )
    search_fields = ("title", "short_description", "owner_urn")
    list_filter = ("visibility", "created_at", "updated_at")
    ordering = ("-created_at",)


@admin.register(ArtifactVersion)
class ArtifactVersionAdmin(admin.ModelAdmin):
    list_display = ("artifact", "created_at", "contents_urn", "slug")
    search_fields = ("contents_urn",)
    list_filter = ("created_at",)


@admin.register(ArtifactVersionMigration)
class ArtifactVersionMigrationAdmin(admin.ModelAdmin):
    list_display = ("artifact_version", "status", "backend", "created_at", "message")
    search_fields = ("message", "source_urn", "destination_urn")
    list_filter = ("status", "backend", "created_at")


@admin.register(ArtifactEvent)
class ArtifactEventAdmin(admin.ModelAdmin):
    list_display = ("artifact_version", "event_type", "event_origin", "timestamp")
    search_fields = ("event_origin",)
    list_filter = ("event_type", "timestamp")


@admin.register(ArtifactTag)
class ArtifactTagAdmin(admin.ModelAdmin):
    list_display = ("tag",)
    search_fields = ("tag",)


@admin.register(ArtifactAuthor)
class ArtifactAuthorAdmin(admin.ModelAdmin):
    list_display = ("artifact", "full_name", "affiliation", "email")
    search_fields = ("full_name", "affiliation", "email")


@admin.register(ArtifactProject)
class ArtifactProjectAdmin(admin.ModelAdmin):
    list_display = ("urn",)
    search_fields = ("urn",)


@admin.register(ArtifactLink)
class ArtifactLinkAdmin(admin.ModelAdmin):
    list_display = ("artifact_version", "urn", "label", "verified", "verified_at")
    search_fields = ("urn", "label")
    list_filter = ("verified",)


@admin.register(ArtifactRole)
class ArtifactRoleAdmin(admin.ModelAdmin):
    list_display = ("artifact", "user", "role", "assigned_by")
    search_fields = ("user", "assigned_by")
    list_filter = ("role",)

from django.contrib import admin
from django.db import transaction
from django.conf import settings

from ..models import (
    Artifact,
    ArtifactLink,
    ArtifactVersion,
    ArtifactVersionMigration,
    ArtifactEvent,
    ArtifactTag,
    ArtifactAuthor,
    ArtifactProject,
    ArtifactVersionLink,
    ArtifactRole,
    CrawlRequest,
    AutoCrawledArtifact,
    ArtifactVersionSetup,
)


class ArtifactAuthorInline(admin.TabularInline):
    model = ArtifactAuthor
    extra = 0


class ArtifactProjectInline(admin.TabularInline):
    model = Artifact.linked_projects.through
    extra = 0


class ArtifactRoleInline(admin.TabularInline):
    model = ArtifactRole
    extra = 0


class ArtifactTagInline(admin.TabularInline):
    model = Artifact.tags.through
    extra = 0


class ArtifactVersionLinkInline(admin.TabularInline):
    model = ArtifactVersionLink
    extra = 0


class ArtifactVersionMigrationInline(admin.TabularInline):
    model = ArtifactVersionMigration
    extra = 0


class ArtifactLinkInline(admin.TabularInline):
    model = ArtifactLink
    extra = 0
    fk_name = "source_artifact"


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
    search_fields = ("title", "short_description", "owner_urn", "citation")
    list_filter = ("visibility", "created_at", "updated_at")
    readonly_fields = ("sharing_key",)
    ordering = ("-created_at",)
    inlines = [
        ArtifactAuthorInline,
        ArtifactProjectInline,
        ArtifactRoleInline,
        ArtifactTagInline,
        ArtifactLinkInline,
    ]


@admin.register(ArtifactVersion)
class ArtifactVersionAdmin(admin.ModelAdmin):
    list_display = ("artifact", "created_at", "contents_urn", "slug")
    search_fields = ("contents_urn",)
    list_filter = ("created_at",)
    inlines = [
        ArtifactVersionLinkInline,
        ArtifactVersionMigrationInline,
    ]


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


@admin.register(ArtifactVersionLink)
class ArtifactVersionLinkAdmin(admin.ModelAdmin):
    list_display = ("artifact_version", "urn", "label", "verified", "verified_at")
    search_fields = ("urn", "label")
    list_filter = ("verified",)


@admin.register(ArtifactRole)
class ArtifactRoleAdmin(admin.ModelAdmin):
    list_display = ("artifact", "user", "role", "assigned_by")
    search_fields = ("user", "assigned_by")
    list_filter = ("role",)


@admin.register(CrawlRequest)
class CrawlRequestAdmin(admin.ModelAdmin):
    list_display = ("url", "requested_by", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("url",)
    readonly_fields = ("status", "created_at", "crawled_data")


@admin.register(AutoCrawledArtifact)
class AutoCrawledArtifactAdmin(admin.ModelAdmin):
    list_display = (
        "source_url",
        "origin_type",
        "title",
        "conference",
        "approved",
        "created_at",
        "updated_at",
    )
    list_filter = ("approved", "origin_type", "conference", "created_at", "updated_at")
    search_fields = ("source_url", "title", "citation", "conference")
    actions = ["approve_artifacts"]

    def _create_artifact(self, crawled_artifact):
        owner_urn = "urn:trovi:user:admin"
        # Format the description
        long_description = (
            f"Source: {crawled_artifact.origin_type}\n\n"
            f"Link: {crawled_artifact.source_url}\n\n"
            f"Conference: {crawled_artifact.conference or 'Not Found'}\n\n"
        )
        if crawled_artifact.abstract:
            long_description += crawled_artifact.abstract

        long_description += (
            "\n\n--\n\n"
            "This artifact was auto-generated from a crawl. Please contact "
            f"Chameleon support at {settings.TROVI_SUPPORT_EMAIL} for more information "
            "or if you are the author and would like to claim the artifact."
        )

        # Check if an artifact with this source_url already exists
        setup = (
            ArtifactVersionSetup.objects.filter(
                type=ArtifactVersionSetup.ArtifactVersionSetupType.SOURCE_CODE,
                arguments__url=crawled_artifact.source_url,
            )
            .select_related("artifact_version__artifact")
            .first()
        )

        if setup and setup.artifact_version and setup.artifact_version.artifact:
            # Update existing artifact
            artifact_to_update = setup.artifact_version.artifact
            artifact_to_update.title = crawled_artifact.title
            artifact_to_update.short_description = long_description[:200]
            artifact_to_update.long_description = long_description
            artifact_to_update.citation = (
                crawled_artifact.citation or "No citation found. View source link."
            )
            artifact_to_update.save()
            new_artifact = artifact_to_update

            # Remove old authors and tags
            new_artifact.authors.all().delete()
            new_artifact.tags.clear()
        else:
            new_artifact = Artifact.objects.create(
                title=crawled_artifact.title,
                short_description=long_description[:200],
                long_description=long_description,
                citation=crawled_artifact.citation
                or "No citation found. View source link.",
                owner_urn=owner_urn,
                visibility=Artifact.Visibility.PUBLIC,
            )

        # Create author records from the JSON data
        if crawled_artifact.authors:
            for author_data in crawled_artifact.authors:
                if isinstance(author_data, str):
                    author_data = {"name": author_data}
                if not isinstance(author_data, dict):
                    continue

                ArtifactAuthor.objects.create(
                    artifact=new_artifact,
                    full_name=author_data.get("name") or settings.TROVI_SUPPORT_FULL_NAME,
                    email=author_data.get("email") or settings.TROVI_SUPPORT_EMAIL,
                    affiliation=author_data.get("affiliation"),
                )
        else:
            ArtifactAuthor.objects.create(
                artifact=new_artifact,
                full_name=settings.TROVI_SUPPORT_FULL_NAME,
                email=settings.TROVI_SUPPORT_EMAIL,
                affiliation=settings.TROVI_SUPPORT_AFFILIATION,
            )

        if crawled_artifact.tags:
            for tag_name in crawled_artifact.tags:
                try:
                    tag = ArtifactTag.objects.get(tag__iexact=tag_name)
                    new_artifact.tags.add(tag)
                except ArtifactTag.DoesNotExist:
                    # Tag does not exist, so we do not create it
                    pass

        if not setup:
            # Create the initial version and setup only if it's a new artifact
            version = ArtifactVersion.objects.create(
                artifact=new_artifact,
                contents_urn=f"urn:trovi:contents:chameleon:{new_artifact.uuid}",
            )
            ArtifactVersionSetup.objects.create(
                artifact_version=version,
                type=ArtifactVersionSetup.ArtifactVersionSetupType.SOURCE_CODE,
                arguments={"url": crawled_artifact.source_url},
            )

    @transaction.atomic
    def approve_artifacts(self, request, queryset):
        for crawled_artifact in queryset.filter(approved=False):
            self._create_artifact(crawled_artifact)
            crawled_artifact.approved = True
            crawled_artifact.save()

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        if obj.approved and (not change or "approved" in form.changed_data):
            self._create_artifact(obj)
        super().save_model(request, obj, form, change)

    approve_artifacts.short_description = "Approve and promote selected artifacts"

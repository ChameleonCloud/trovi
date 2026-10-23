from urllib.parse import urljoin

from django.core.management.base import BaseCommand

from trovi.auth.providers import get_client_by_name
from trovi.models import Artifact, ArtifactComment, UserProfile

CHAMELEON_URN_PREFIX = "urn:trovi:user:chameleon:"


class Command(BaseCommand):
    help = (
        "Create profiles for artifact owners and comment authors who have none, "
        "using their email and name from Keycloak. The Trovi admin client's "
        "service account needs the realm-management view-users role."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Don't save changes, just print what would be done.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        urns = (
            set(Artifact.objects.values_list("owner_urn", flat=True))
            | set(ArtifactComment.objects.values_list("user", flat=True))
        ) - set(UserProfile.objects.values_list("urn", flat=True))

        keycloak = get_client_by_name("CHAMELEON_KEYCLOAK")
        users_url = urljoin(
            keycloak.server_url, f"auth/admin/realms/{keycloak.realm_name}/users"
        )

        created = 0
        for urn in sorted(u for u in urns if u.startswith(CHAMELEON_URN_PREFIX)):
            username = urn.removeprefix(CHAMELEON_URN_PREFIX)
            # A fresh token per lookup, so a long run can't outlive the token
            token = keycloak.get_client_token()["access_token"]
            response = keycloak.session.get(
                users_url,
                params={"username": username, "exact": "true"},
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            user = next((u for u in response.json() if u["username"] == username), {})
            if not user.get("email"):
                self.stdout.write(self.style.WARNING(f"No Keycloak email for {urn}"))
                continue

            full_name = f"{user.get('firstName', '')} {user.get('lastName', '')}"
            self.stdout.write(f"{urn} -> {user['email']}")
            if not dry_run:
                UserProfile.objects.get_or_create(
                    urn=urn,
                    defaults={
                        "email": user["email"],
                        "full_name": full_name.strip(),
                        "keycloak_sub": user["id"],
                    },
                )
            created += 1

        verb = "Would create" if dry_run else "Created"
        self.stdout.write(self.style.SUCCESS(f"{verb} {created} profiles"))

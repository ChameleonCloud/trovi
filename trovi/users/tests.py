import io
import json
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.reverse import reverse

from trovi.api.tests import APITest
from trovi.auth.providers import get_client_by_name
from trovi.common.tokens import JWT
from trovi.models import UserProfile
from util.test import artifact_don_quixote

USER_PROFILE_PATH = reverse("UserProfile")


class TestUserProfile(TestCase, APITest):
    def setUp(self):
        # Each token exchange rewrites the profile, so exchange before setting it
        self.read_path = self.authenticate_url(USER_PROFILE_PATH)
        self.write_path = self.authenticate_url(
            USER_PROFILE_PATH, [JWT.Scopes.ARTIFACTS_WRITE]
        )
        self.profile, _ = UserProfile.objects.update_or_create(
            urn=JWT.from_jws(self.get_test_token()).to_urn(),
            defaults={"email": "sancho@rocinante.io"},
        )

    def patch_profile(self, data: dict, path: str = None):
        return self.client.patch(
            path or self.write_path,
            content_type="application/json",
            data=json.dumps(data),
        )

    def test_get_profile(self):
        response = self.client.get(self.read_path)
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.json())
        self.assertEqual(
            response.json(),
            {"email": "sancho@rocinante.io", "comment_notifications": True},
        )

    def test_disable_comment_notifications(self):
        response = self.patch_profile({"comment_notifications": False})
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.json())
        self.assertFalse(response.json()["comment_notifications"])
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.comment_notifications)

    def test_email_is_read_only(self):
        self.patch_profile({"email": "dulcinea@toboso.gov"})
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.email, "sancho@rocinante.io")

    def test_update_requires_write_scope(self):
        response = self.patch_profile(
            {"comment_notifications": False}, path=self.read_path
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.comment_notifications)

    def test_requires_token(self):
        response = self.client.get(USER_PROFILE_PATH)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_missing_profile(self):
        self.profile.delete()
        response = self.client.get(self.read_path)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class TestBackfillUserProfiles(TestCase):
    owner = artifact_don_quixote.owner_urn
    commenter = "urn:trovi:user:chameleon:dulcinea@toboso.gov"
    no_email_user = "urn:trovi:user:chameleon:sancho@rocinante.io"

    @staticmethod
    def keycloak_users(url, params, headers):
        username = params["username"]
        email = "" if username.startswith("sancho") else username
        user = {"id": "kc-id", "username": username, "email": email, "firstName": "Don"}
        return mock.Mock(json=mock.Mock(return_value=[user]))

    def backfill(self, *args):
        keycloak = get_client_by_name("CHAMELEON_KEYCLOAK")
        token = {"access_token": "token"}
        with mock.patch.object(keycloak, "get_client_token", return_value=token):
            with mock.patch.object(
                keycloak.session, "get", side_effect=self.keycloak_users
            ):
                call_command("backfill_user_profiles", *args, stdout=io.StringIO())

    def test_creates_owner_and_commenter_profiles(self):
        artifact_don_quixote.comments.create(user=self.commenter, description="Hi")
        self.backfill()
        owner = UserProfile.objects.get(urn=self.owner)
        self.assertEqual(owner.email, "donquixote@rosinante.io")
        self.assertEqual(owner.full_name, "Don")
        self.assertEqual(owner.keycloak_sub, "kc-id")
        self.assertTrue(UserProfile.objects.filter(urn=self.commenter).exists())

    def test_keeps_existing_profiles(self):
        UserProfile.objects.create(
            urn=self.owner, email="old@rosinante.io", comment_notifications=False
        )
        self.backfill()
        owner = UserProfile.objects.get(urn=self.owner)
        self.assertEqual(owner.email, "old@rosinante.io")
        self.assertFalse(owner.comment_notifications)

    def test_skips_users_without_email(self):
        artifact_don_quixote.comments.create(user=self.no_email_user, description="Hi")
        self.backfill()
        self.assertFalse(UserProfile.objects.filter(urn=self.no_email_user).exists())

    def test_dry_run(self):
        self.backfill("--dry-run")
        self.assertFalse(UserProfile.objects.exists())

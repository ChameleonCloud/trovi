import json
import os

import jwt
from django.conf import settings
from django.test import TestCase
from rest_framework import status
from rest_framework.renderers import JSONRenderer
from rest_framework.reverse import reverse

from trovi.auth import providers
from trovi.common.tokens import TokenTypes


class AuthTestCase(TestCase):
    renderer = JSONRenderer()
    maxDiff = None

    dummy_jwt = jwt.encode(
        payload={"name": "Trovi Test", "sub": "test@trovi", "aud": settings.TROVI_FQDN},
        key=settings.AUTH_TROVI_TOKEN_SIGNING_KEY,
        algorithm=settings.AUTH_TROVI_TOKEN_SIGNING_ALGORITHM,
    )

    @staticmethod
    def token_grant_path():
        return reverse("TokenGrant")


class TestTokenGrant(AuthTestCase):
    def test_endpoint_works(self):
        try:
            base_response = self.client.post(
                self.token_grant_path(),
                content_type="application/json",
                data={
                    "grant_type": "token_exchange",
                    "subject_token": self.dummy_jwt,
                    "subject_token_type": TokenTypes.JWT_TOKEN_TYPE.value,
                },
            )
            self.assertIsNotNone(base_response)
        except Exception as e:
            self.fail(str(e))

    def test_invalid_token(self):
        base_response = self.client.post(
            self.token_grant_path(),
            content_type="application/json",
            data={
                "grant_type": "token_exchange",
                "subject_token": self.dummy_jwt,
                "subject_token_type": TokenTypes.JWT_TOKEN_TYPE.value,
            },
        )
        self.assertEqual(base_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_valid_token(self):
        for provider_name, provider in providers._idp_clients.items():
            test_username = os.environ.get(f"{provider_name}_TEST_USER_USERNAME")
            test_password = os.environ.get(f"{provider_name}_TEST_USER_PASSWORD")
            test_client_id = os.environ.get(f"{provider_name}_TEST_CLIENT_ID")
            test_client_secret = os.environ.get(f"{provider_name}_TEST_CLIENT_SECRET")

            valid_token = provider.get_user_token(
                test_username, test_password, test_client_id, test_client_secret
            )

            response = self.client.post(
                self.token_grant_path(),
                content_type="application/json",
                data={
                    "grant_type": "token_exchange",
                    "subject_token": valid_token,
                    "subject_token_type": TokenTypes.JWT_TOKEN_TYPE.value,
                },
            )

            self.assertEqual(
                response.status_code,
                status.HTTP_201_CREATED,
                msg=json.loads(response.content),
            )

            # Test HTTP response data
            response_data = json.loads(response.content)
            self.assertEqual(
                response_data["issued_token_type"],
                TokenTypes.ACCESS_TOKEN_TYPE.value,
            )
            self.assertEqual(response_data["token_type"], "bearer")
            self.assertEqual(
                response_data["expires_in"], settings.AUTH_TROVI_TOKEN_LIFESPAN_SECONDS
            )
            self.assertEqual(response_data["scope"], "artifacts:read")

            # Test JWT data
            try:
                token = jwt.decode(
                    response_data["access_token"],
                    key=settings.AUTH_TROVI_TOKEN_SIGNING_KEY,
                    algorithms=[settings.AUTH_TROVI_TOKEN_SIGNING_ALGORITHM],
                    audience=settings.TROVI_FQDN,
                )
            except Exception as e:
                self.fail(e)
            self.assertEqual(
                os.environ.get("CHAMELEON_KEYCLOAK_TEST_USER_USERNAME"), token["azp"]
            )
            self.assertEqual(settings.TROVI_FQDN, token["aud"])
            self.assertEqual(token["azp"], token["sub"])
            self.assertEqual(
                token["exp"], token["iat"] + settings.AUTH_TROVI_TOKEN_LIFESPAN_SECONDS
            )
            self.assertEqual(token["scope"], response_data["scope"])

    def test_introspection(self):
        # TODO
        pass


class TestChameloneCloudKeycloakProvider(AuthTestCase):
    """
    Unit tests for The Chameleon Cloud Keycloak IdP
    """

    def test_signing_key_retrieval(self):
        # TODO
        pass

import json
from datetime import datetime, timezone
from unittest import mock

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.test import TestCase
from jwt import PyJWK
from jwt.algorithms import RSAAlgorithm
from rest_framework import status
from rest_framework.renderers import JSONRenderer
from rest_framework.reverse import reverse

from trovi.auth.providers import KeycloakIdentityProvider
from trovi.common.tokens import TokenTypes
from trovi.models import UserProfile
from util.test import TEST_USERNAME


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
        keycloak_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = int(datetime.now(timezone.utc).timestamp())
        subject = {
            "iss": settings.CHAMELEON_KEYCLOAK_SERVER_URL,
            "aud": [settings.CHAMELEON_KEYCLOAK_TROVI_ADMIN_CLIENT_ID],
            "azp": "portal",
            "sub": "keycloak-user-id",
            "preferred_username": TEST_USERNAME,
            "email": TEST_USERNAME,
            "name": "Miguel de Cervantes",
            "iat": now,
            "exp": now + 300,
        }
        valid_token = jwt.encode(subject, keycloak_key, algorithm="RS256")
        signing_key = PyJWK(
            RSAAlgorithm.to_jwk(keycloak_key.public_key(), as_dict=True)
        )

        with mock.patch.object(
            KeycloakIdentityProvider,
            "signing_keys",
            new_callable=mock.PropertyMock,
            return_value=[signing_key],
        ):
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
        self.assertEqual(TEST_USERNAME, token["sub"])
        self.assertEqual([settings.TROVI_FQDN], token["aud"])
        self.assertIn(token["azp"], settings.AUTH_ISSUERS.values())
        self.assertEqual(
            token["exp"], token["iat"] + settings.AUTH_TROVI_TOKEN_LIFESPAN_SECONDS
        )
        self.assertEqual(token["scope"], response_data["scope"])

        # Test user profile recorded from the subject token
        profile = UserProfile.objects.get(
            urn=f"urn:trovi:user:{token['azp']}:{token['sub']}"
        )
        self.assertEqual(profile.email, subject["email"])
        self.assertEqual(profile.keycloak_sub, subject["sub"])

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

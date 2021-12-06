from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt import views
from rest_framework_simplejwt.exceptions import AuthenticationFailed

from trovi.api.parsers import JSONSchemaParser
from trovi.auth import schema
from trovi.auth.providers import get_subject_token_provider
from trovi.auth.serializers import TokenGrantRequestSerializer
from trovi.auth.tokens import JWT


class TokenGrant(views.TokenViewBase):
    """
    Receives a subject token from a client, exchanges it for a Trovi token, and returns
    that token to the client
    """

    serializer_class = TokenGrantRequestSerializer
    parser_classes = [JSONSchemaParser]

    def get_parser_context(self, http_request: Request) -> dict:
        context = super(TokenGrant, self).get_parser_context(http_request)
        context["schema"] = schema.TokenGrantSchema

        return context


class TokenInspect(views.TokenVerifyView):
    """
    Performs OAuth2.0 Token Introspection on a subject token
    """

    lookup_url_kwarg = "token"

    def post(self, request: Request, *args, **kwargs) -> Response:
        jws = self.kwargs.get(self.lookup_url_kwarg)
        if not jws:
            raise ValidationError("Missing 'token' parameter")
        jwt = JWT.from_jws(jws, validate=False)
        provider = get_subject_token_provider(jwt)
        introspection = provider.introspect_token(jwt)
        if not introspection:
            raise AuthenticationFailed(
                f"Token introspection not available for "
                f"Identity Provider {provider.get_name()}"
            )
        return Response(
            {
                "token": introspection.token,
                "exp": introspection.exp,
                "scope": introspection.scope,
                "username": introspection.username,
                "client_id": introspection.client_id,
                "active": introspection.active,
            }
        )

from rest_framework.request import Request
from rest_framework_simplejwt import views

from trovi.api.parsers import JSONSchemaParser
from trovi.auth import schema
from trovi.auth.serializers import TokenGrantRequestSerializer


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

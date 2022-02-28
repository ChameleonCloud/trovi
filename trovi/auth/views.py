from rest_framework import generics
from rest_framework.parsers import JSONParser

from trovi.auth.serializers import TokenGrantRequestSerializer


class TokenGrant(generics.CreateAPIView):
    """
    Receives a subject token from a client, exchanges it for a Trovi token, and returns
    that token to the client
    """

    serializer_class = TokenGrantRequestSerializer
    parser_classes = [JSONParser]

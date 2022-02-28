from rest_framework import views
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.schemas import SchemaGenerator


class DocumentationView(views.APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request: Request) -> Response:
        generator = SchemaGenerator(title="Trovi API")
        schema = generator.get_schema()

        return Response(schema)

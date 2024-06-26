from rest_framework import serializers


class ArtifactImportSerializer(serializers.Serializer):
    github_url = serializers.CharField()

from rest_framework import serializers

from trovi.models import UserProfile


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ["email", "comment_notifications"]
        read_only_fields = ["email"]

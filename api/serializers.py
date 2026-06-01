from rest_framework import serializers


class BalancedReviewSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    rating = serializers.IntegerField()
    text = serializers.CharField()
    created_at = serializers.DateTimeField()


class AgentCanteenSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    address = serializers.CharField()
    rating = serializers.FloatField()
    reviews = BalancedReviewSerializer(many=True)

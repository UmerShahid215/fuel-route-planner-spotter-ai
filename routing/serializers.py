from django.conf import settings
from rest_framework import serializers


class RoutePlanRequestSerializer(serializers.Serializer):
    start = serializers.CharField(max_length=200, trim_whitespace=True)
    finish = serializers.CharField(max_length=200, trim_whitespace=True)
    start_fuel_gallons = serializers.FloatField(required=False, min_value=0)
    include_geometry = serializers.BooleanField(required=False, default=True)

    def validate_start_fuel_gallons(self, value):
        cfg = settings.FUEL_ROUTE
        tank = cfg["VEHICLE_RANGE_MILES"] / cfg["MILES_PER_GALLON"]
        if value > tank:
            raise serializers.ValidationError(f"Cannot exceed tank capacity of {tank:g} gallons.")
        return value

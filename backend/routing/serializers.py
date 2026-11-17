from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .services.weather import FORECAST_DAYS


class PlaceSerializer(serializers.Serializer):
    """A place picked from autocomplete (with coordinates) or free text to be geocoded."""

    label = serializers.CharField(max_length=200)
    lat = serializers.FloatField(min_value=-90, max_value=90, required=False)
    lon = serializers.FloatField(min_value=-180, max_value=180, required=False)

    def validate(self, attrs):
        if ("lat" in attrs) != ("lon" in attrs):
            raise serializers.ValidationError("Provide both lat and lon, or neither.")
        return attrs


def validate_departure(value):
    now = timezone.now()
    if value < now - timedelta(hours=1):
        raise serializers.ValidationError("Departure cannot be in the past.")
    if value > now + timedelta(days=FORECAST_DAYS - 2):
        raise serializers.ValidationError(f"Departure must be within {FORECAST_DAYS - 2} days (forecast horizon).")
    return value


class PlanRequestSerializer(serializers.Serializer):
    origin = PlaceSerializer()
    destination = PlaceSerializer()
    departure = serializers.DateTimeField(validators=[validate_departure])
    load_lb = serializers.FloatField(min_value=0, max_value=200_000)
    interval_mi = serializers.ChoiceField(choices=[10, 25, 50], default=25)
    hos = serializers.BooleanField(default=True)


class CoordinateListField(serializers.ListField):
    child = serializers.ListField(child=serializers.FloatField(), min_length=2, max_length=2)


class HeatmapRequestSerializer(serializers.Serializer):
    routes = serializers.ListField(child=CoordinateListField(min_length=2, max_length=20_000), min_length=1, max_length=3)
    departure = serializers.DateTimeField(validators=[validate_departure])
    load_lb = serializers.FloatField(min_value=0, max_value=200_000)

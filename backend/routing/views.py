import logging

from django.conf import settings
from django.http import FileResponse, Http404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .serializers import HeatmapRequestSerializer, PlanRequestSerializer
from .services import geocoding, heatmap
from .services.geocoding import LocationNotFound, Place
from .services.http import UpstreamError
from .services.planner import NoRouteFound, plan_trip

logger = logging.getLogger(__name__)


def exception_handler(exc, context):
    """Map domain errors to clean JSON responses: bad input -> 400, provider failure -> 502."""
    if isinstance(exc, (LocationNotFound, NoRouteFound)):
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, UpstreamError):
        logger.warning("Upstream failure: %s", exc)
        return Response(
            {"detail": f"The {exc.service} service is unavailable right now. Please try again shortly."},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    return drf_exception_handler(exc, context)


def _place(data: dict) -> Place:
    if "lat" in data:
        return Place(label=data["label"], lon=data["lon"], lat=data["lat"])
    return geocoding.resolve(data["label"])


@api_view(["GET"])
def health(request):
    return Response({"status": "ok"})


@api_view(["GET"])
def geocode(request):
    query = request.query_params.get("q", "")
    if len(query.strip()) < 2:
        return Response({"results": []})
    return Response({"results": [p.as_dict() for p in geocoding.search(query)]})


@api_view(["POST"])
def plan(request):
    serializer = PlanRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    origin, destination = _place(data["origin"]), _place(data["destination"])
    if (origin.lon, origin.lat) == (destination.lon, destination.lat):
        return Response({"detail": "Origin and destination are the same."}, status=status.HTTP_400_BAD_REQUEST)
    result = plan_trip(
        origin=origin,
        destination=destination,
        departure=data["departure"],
        load_lb=data["load_lb"],
        interval_mi=data["interval_mi"],
        hos_enabled=data["hos"],
    )
    return Response(result)


@api_view(["POST"])
def weather_heatmap(request):
    serializer = HeatmapRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    routes = [[(c[0], c[1]) for c in route] for route in data["routes"]]
    return Response(heatmap.build(routes, data["departure"], data["load_lb"]))


def spa_index(request):
    """Serve the React app's index.html for client-side routes (production build only)."""
    index = settings.FRONTEND_DIST / "index.html"
    if not index.exists():
        raise Http404("Frontend not built. Run `npm run build` in frontend/ or use the Vite dev server.")
    return FileResponse(index.open("rb"), content_type="text/html")

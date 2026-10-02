from urllib.parse import urlencode

from django.shortcuts import render
from django.urls import reverse
from django.views import View
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RoutePlanRequestSerializer
from .services.geocoding import GeocodingError
from .services.optimizer import InfeasibleRoute
from .services.planner import plan_trip
from .services.routing_client import RoutingError

ERROR_STATUS = {
    GeocodingError: status.HTTP_400_BAD_REQUEST,
    InfeasibleRoute: status.HTTP_422_UNPROCESSABLE_ENTITY,
    RoutingError: status.HTTP_502_BAD_GATEWAY,
}


def run_plan(data):
    serializer = RoutePlanRequestSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    params = serializer.validated_data
    try:
        result = plan_trip(params["start"], params["finish"], params.get("start_fuel_gallons"))
    except tuple(ERROR_STATUS) as exc:
        return params, None, (ERROR_STATUS[type(exc)], str(exc))
    return params, result, None


class RoutePlanView(APIView):
    def get(self, request):
        return self._respond(request, request.query_params)

    def post(self, request):
        return self._respond(request, request.data)

    def _respond(self, request, data):
        params, result, error = run_plan(data)
        if error:
            return Response({"detail": error[1]}, status=error[0])
        query = {"start": params["start"], "finish": params["finish"]}
        if "start_fuel_gallons" in params:
            query["start_fuel_gallons"] = params["start_fuel_gallons"]
        result["map_url"] = request.build_absolute_uri(f"{reverse('route-map')}?{urlencode(query)}")
        if not params["include_geometry"]:
            result["route"].pop("geometry")
        return Response(result)


class RouteMapView(View):
    def get(self, request):
        serializer = RoutePlanRequestSerializer(data=request.GET)
        if not serializer.is_valid():
            return render(request, "routing/map.html", {"error": serializer.errors}, status=400)
        _, result, error = run_plan(request.GET)
        if error:
            return render(request, "routing/map.html", {"error": error[1]}, status=error[0])
        return render(request, "routing/map.html", {"plan": result})

from routing.services import geo
from routing.services.routing import Route


def straight_route(miles: float, mph: float = 60, points: int = 50) -> Route:
    """A due-north route of the given length driven at constant speed."""
    total_m = miles * geo.METERS_PER_MILE
    coords = [geo.destination((-100.0, 35.0), 0, total_m * i / (points - 1)) for i in range(points)]
    seg = [geo.haversine_m(a, b) for a, b in zip(coords, coords[1:])]
    speed = mph * geo.METERS_PER_MILE / 3600
    return Route(coords=coords, seg_distance_m=seg, seg_drive_s=[d / speed for d in seg], summary="I 0")

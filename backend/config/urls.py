from django.urls import include, path, re_path

from routing.views import spa_index

urlpatterns = [
    path("api/", include("routing.urls")),
    re_path(r"^(?!api/).*$", spa_index),
]

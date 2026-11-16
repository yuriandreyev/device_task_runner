from django.urls import path

from backend.tasks.views import health

urlpatterns = [path("health/", health, name="health")]

from django.urls import path

from devices.views import health

urlpatterns = [path("health/", health, name="health")]

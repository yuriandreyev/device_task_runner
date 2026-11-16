from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    """Liveness probe; database readiness is checked separately by Compose."""
    return JsonResponse({"status": "ok"})

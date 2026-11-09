"""
Mode démo (DEMO_MODE=true dans le .env de l'instance de démo uniquement).

Les visiteurs partagent les mêmes comptes : on bloque ce qui gênerait les suivants
(mot de passe, email, comptes supprimés ou désactivés). Tout le reste fonctionne ;
les données sont remises à zéro chaque nuit (seed_demo --reset).
"""
import re

from django.conf import settings
from django.http import JsonResponse

BLOCKED = [
    (re.compile(r'^/api/users/change_password/?$'), {'POST'}),
    (re.compile(r'^/api/users/update_profile/?$'), {'PUT', 'PATCH'}),
    (re.compile(r'^/api/users/\d+/?$'), {'PUT', 'PATCH', 'DELETE'}),
    (re.compile(r'^/api/users/\d+/toggle_active/?$'), {'POST'}),
    (re.compile(r'^/api/auth/password-reset(/confirm)?/?$'), {'POST'}),
]
MESSAGE = "Action désactivée dans la démo : les comptes sont partagés par tous les visiteurs."


class DemoModeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, 'DEMO_MODE', False):
            for pattern, methods in BLOCKED:
                if request.method in methods and pattern.match(request.path):
                    return JsonResponse({'error': MESSAGE}, status=403)
        return self.get_response(request)

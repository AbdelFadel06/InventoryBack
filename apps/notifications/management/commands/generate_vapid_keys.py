"""
Génère la paire de clés des notifications téléphone, à ajouter au .env du serveur :

    venv/bin/python manage.py generate_vapid_keys >> .env

Les clés ne s'affichent pas à l'écran si on redirige vers le fichier. Refuse de
tourner si des clés existent déjà : en changer désabonnerait tous les téléphones.
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


class Command(BaseCommand):
    help = "Génère VAPID_PUBLIC_KEY et VAPID_PRIVATE_KEY pour le .env"

    def handle(self, *args, **options):
        if settings.VAPID_PUBLIC_KEY or settings.VAPID_PRIVATE_KEY:
            raise CommandError("Des clés VAPID sont déjà dans le .env : rien n'a été généré.")
        key = ec.generate_private_key(ec.SECP256R1())
        private = key.private_numbers().private_value.to_bytes(32, 'big')
        public = key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint,
        )
        self.stdout.write(f"VAPID_PUBLIC_KEY={_b64(public)}")
        self.stdout.write(f"VAPID_PRIVATE_KEY={_b64(private)}")

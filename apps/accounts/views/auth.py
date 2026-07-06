# apps/accounts/views/auth.py
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from apps.accounts.models import User


# ── Email templates ───────────────────────────────────────────────────────────

def _email_html(title: str, greeting: str, body_html: str, cta_url: str, cta_text: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="fr">
<body style="margin:0;padding:0;background:#F0F4F8;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#F0F4F8;padding:40px 20px;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
        style="background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);max-width:560px;width:100%;">
        <tr>
          <td style="background:linear-gradient(135deg,#0F172A,#1E293B);padding:32px 40px;text-align:center;">
            <div style="font-size:22px;font-weight:700;color:#fff;letter-spacing:-0.5px;">ShopM</div>
            <div style="font-size:12px;color:rgba(255,255,255,0.5);margin-top:4px;">Gestion commerciale</div>
          </td>
        </tr>
        <tr>
          <td style="padding:40px;">
            <h1 style="font-size:20px;font-weight:700;color:#0F172A;margin:0 0 6px;">{title}</h1>
            <p style="font-size:14px;color:#64748B;margin:0 0 20px;">{greeting}</p>
            <div style="font-size:14px;color:#374151;line-height:1.7;margin:0 0 32px;">{body_html}</div>
            <div style="text-align:center;margin-bottom:32px;">
              <a href="{cta_url}"
                style="display:inline-block;background:linear-gradient(135deg,#3B82F6,#1D4ED8);color:#fff;
                text-decoration:none;padding:14px 36px;border-radius:10px;font-size:15px;font-weight:600;">
                {cta_text}
              </a>
            </div>
            <p style="font-size:12px;color:#94A3B8;margin:0;">
              Si le bouton ne fonctionne pas, copiez ce lien dans votre navigateur :<br>
              <a href="{cta_url}" style="color:#3B82F6;word-break:break-all;font-size:11px;">{cta_url}</a>
            </p>
          </td>
        </tr>
        <tr>
          <td style="background:#F8FAFC;padding:18px 40px;text-align:center;border-top:1px solid #E2E8F0;">
            <p style="font-size:11px;color:#94A3B8;margin:0;">
              Ce message a été envoyé automatiquement. Ne pas répondre à cet email.
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _activation_html(user: User, url: str) -> str:
    return _email_html(
        title="Bienvenue sur ShopM !",
        greeting=f"Bonjour {user.first_name},",
        body_html=(
            "Un compte vient d'être créé pour vous sur <strong>ShopM</strong>.<br><br>"
            "Cliquez sur le bouton ci-dessous pour définir votre propre mot de passe "
            "et activer votre compte. Ce lien est valable <strong>3 jours</strong>."
        ),
        cta_url=url,
        cta_text="Activer mon compte",
    )


def _reset_html(user: User, url: str) -> str:
    return _email_html(
        title="Réinitialisation du mot de passe",
        greeting=f"Bonjour {user.first_name},",
        body_html=(
            "Nous avons reçu une demande de réinitialisation de mot de passe pour votre compte.<br><br>"
            "Cliquez sur le bouton ci-dessous pour choisir un nouveau mot de passe. "
            "Ce lien est valable <strong>3 jours</strong>.<br><br>"
            "Si vous n'êtes pas à l'origine de cette demande, ignorez simplement cet email."
        ),
        cta_url=url,
        cta_text="Réinitialiser mon mot de passe",
    )


# ── Helpers publics ───────────────────────────────────────────────────────────

def _send(subject: str, text: str, html: str, to: str) -> None:
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to],
        reply_to=[settings.EMAIL_HOST_USER],
        headers={
            'X-Mailer': 'ShopM',
        },
    )
    msg.attach_alternative(html, 'text/html')
    msg.send(fail_silently=False)


def send_activation_email(user: User) -> None:
    uid   = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    url   = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
    _send(
        subject=f'Bienvenue sur ShopM, {user.first_name} — Activez votre compte',
        text=f'Bonjour {user.first_name},\n\nActivez votre compte ici : {url}\n\nCe lien expire dans 3 jours.',
        html=_activation_html(user, url),
        to=user.email,
    )


# ── Views ─────────────────────────────────────────────────────────────────────

class PasswordResetRequestView(APIView):
    """POST /api/auth/password-reset/ — envoie un email de reset"""
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        if not email:
            return Response({'error': 'Email requis.'}, status=400)

        # Ne pas révéler si l'email existe ou non
        msg = {'message': 'Si cet email est enregistré, un lien de réinitialisation a été envoyé.'}

        try:
            user = User.objects.get(email__iexact=email, is_active=True)
        except User.DoesNotExist:
            return Response(msg)

        uid   = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        url   = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"

        try:
            _send(
                subject=f'Réinitialisation de votre mot de passe ShopM, {user.first_name}',
                text=f'Bonjour {user.first_name},\n\nRéinitialisez votre mot de passe ici : {url}\n\nCe lien expire dans 3 jours.\n\nSi vous n\'êtes pas à l\'origine de cette demande, ignorez cet email.',
                html=_reset_html(user, url),
                to=user.email,
            )
        except Exception:
            return Response(
                {'error': 'Impossible d\'envoyer l\'email. Contactez un administrateur.'},
                status=503,
            )

        return Response(msg)


class PasswordResetConfirmView(APIView):
    """POST /api/auth/password-reset/confirm/ — valide le token et change le mot de passe"""
    permission_classes = [AllowAny]

    def post(self, request):
        uid      = request.data.get('uid', '')
        token    = request.data.get('token', '')
        password = request.data.get('password', '')

        if not uid or not token or not password:
            return Response({'error': 'Données manquantes.'}, status=400)

        if len(password) < 8:
            return Response(
                {'error': 'Le mot de passe doit contenir au moins 8 caractères.'},
                status=400,
            )

        try:
            pk   = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=pk, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({'error': 'Lien invalide.'}, status=400)

        if not default_token_generator.check_token(user, token):
            return Response(
                {'error': 'Ce lien a expiré ou est invalide. Demandez un nouveau lien.'},
                status=400,
            )

        user.set_password(password)
        user.email_verified = True
        user.save(update_fields=['password', 'email_verified'])

        return Response({'message': 'Mot de passe modifié avec succès. Vous pouvez maintenant vous connecter.'})

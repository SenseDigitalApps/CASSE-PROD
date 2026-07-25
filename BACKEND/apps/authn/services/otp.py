"""
OTP service for generating and validating OTP codes.
Uses Redis for storage with automatic expiration.
"""
import logging
import secrets
import uuid
from typing import Optional, Tuple

from django.conf import settings
from django.core.cache import cache
from django.contrib.auth import get_user_model

User = get_user_model()
logger = logging.getLogger(__name__)


def generate_otp_code() -> str:
    """Genera un código OTP numérico."""
    return ''.join(
        str(secrets.randbelow(10)) for _ in range(settings.OTP_CODE_LENGTH)
    )


def generate_session_token() -> str:
    """Genera un token de sesión único para el flujo de OTP."""
    return str(uuid.uuid4())


def _ttl_seconds() -> int:
    return settings.OTP_EXPIRATION_MINUTES * 60


def store_otp(user_id: str, session_token: str, otp_code: str, purpose: str = 'LOGIN') -> bool:
    """
    Almacena el OTP vigente para un usuario.

    Se guarda:
    - otp:{purpose}:{user_id}              → código vigente (último gana)
    - otp:{purpose}:{user_id}:session      → session_token vigente
    - session:{session_token}              → user_id
    - otp:attempts:{user_id}               → intentos del código vigente
    """
    try:
        ttl = _ttl_seconds()
        otp_code = str(otp_code).strip()

        # Invalidar sesión OTP anterior (si existe).
        previous_session = cache.get(f'otp:{purpose}:{user_id}:session')
        if previous_session and previous_session != session_token:
            cache.delete(f'session:{previous_session}')
            cache.delete(f'otp:{purpose}:{user_id}:{previous_session}')
            cache.delete(f'otp:attempts:{user_id}:{previous_session}')

        cache.set(f'otp:{purpose}:{user_id}', otp_code, timeout=ttl)
        cache.set(f'otp:{purpose}:{user_id}:session', session_token, timeout=ttl)
        # Compatibilidad con lecturas antiguas keyed por session.
        cache.set(f'otp:{purpose}:{user_id}:{session_token}', otp_code, timeout=ttl)
        cache.set(f'session:{session_token}', user_id, timeout=ttl)
        cache.set(f'otp:attempts:{user_id}', 0, timeout=ttl)
        cache.set(f'otp:attempts:{user_id}:{session_token}', 0, timeout=ttl)

        if getattr(settings, 'OTP_LOG_CODES', False):
            logger.info(
                'OTP issued purpose=%s user_id=%s session=%s code=%s',
                purpose, user_id, session_token, otp_code,
            )
        else:
            logger.info(
                'OTP issued purpose=%s user_id=%s session=%s',
                purpose, user_id, session_token,
            )
        return True
    except Exception as exc:
        logger.error('Error al almacenar OTP: %s', exc, exc_info=True)
        return False


def get_otp(user_id: str, session_token: str, purpose: str = 'LOGIN') -> Optional[str]:
    """Obtiene el OTP vigente del usuario (último emitido)."""
    try:
        latest = cache.get(f'otp:{purpose}:{user_id}')
        if latest:
            return str(latest).strip()
        legacy = cache.get(f'otp:{purpose}:{user_id}:{session_token}')
        return str(legacy).strip() if legacy is not None else None
    except Exception as exc:
        logger.error('Error al obtener OTP: %s', exc, exc_info=True)
        return None


def validate_otp(
    user_id: str,
    session_token: str,
    otp_code: str,
    purpose: str = 'LOGIN',
) -> Tuple[bool, str]:
    """Valida el OTP vigente del usuario."""
    try:
        otp_code = str(otp_code or '').strip()
        attempts_key = f'otp:attempts:{user_id}'
        attempts = int(cache.get(attempts_key, 0) or 0)

        if attempts >= settings.OTP_MAX_ATTEMPTS:
            return False, 'Máximo número de intentos excedido. Solicita un nuevo código.'

        latest_session = cache.get(f'otp:{purpose}:{user_id}:session')
        if latest_session and str(latest_session) != str(session_token):
            cache.set(attempts_key, attempts + 1, timeout=_ttl_seconds())
            remaining = settings.OTP_MAX_ATTEMPTS - (attempts + 1)
            return (
                False,
                'Esa sesión ya no es válida. Vuelve a iniciar sesión y usa el '
                f'código del correo más reciente. Intentos restantes: {remaining}',
            )

        stored_otp = get_otp(user_id, session_token, purpose)
        if not stored_otp:
            cache.set(attempts_key, attempts + 1, timeout=_ttl_seconds())
            return False, 'Código OTP no encontrado o expirado. Solicita un nuevo código.'

        if stored_otp != otp_code:
            cache.set(attempts_key, attempts + 1, timeout=_ttl_seconds())
            remaining = settings.OTP_MAX_ATTEMPTS - (attempts + 1)
            logger.warning(
                'OTP mismatch user_id=%s received=%s stored=%s remaining=%s',
                user_id, otp_code, stored_otp, remaining,
            )
            return False, f'Código OTP incorrecto. Intentos restantes: {remaining}'

        cache.delete(f'otp:{purpose}:{user_id}')
        cache.delete(f'otp:{purpose}:{user_id}:session')
        cache.delete(f'otp:{purpose}:{user_id}:{session_token}')
        cache.delete(attempts_key)
        cache.delete(f'otp:attempts:{user_id}:{session_token}')

        logger.info('OTP validado correctamente para usuario %s', user_id)
        return True, 'OTP válido'
    except Exception as exc:
        logger.error('Error al validar OTP: %s', exc, exc_info=True)
        return False, 'Error al validar código OTP'


def get_user_from_session_token(session_token: str) -> Optional[User]:
    """Obtiene el usuario desde un session token."""
    try:
        user_id = cache.get(f'session:{session_token}')
        if not user_id:
            return None
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.warning('Usuario no encontrado para session token %s', session_token)
        return None
    except Exception as exc:
        logger.error('Error al obtener usuario desde session token: %s', exc, exc_info=True)
        return None


def can_resend_otp(user_id: str) -> Tuple[bool, str]:
    """Verifica si el usuario puede solicitar un nuevo OTP."""
    try:
        resend_count = cache.get(f'otp:resend_count:{user_id}', 0)
        if resend_count >= settings.OTP_MAX_RESEND_PER_HOUR:
            return False, 'Máximo de reenvíos alcanzado. Espera 1 hora antes de solicitar otro código.'

        if cache.get(f'otp:resend_cooldown:{user_id}'):
            return (
                False,
                f'Espera {settings.OTP_RESEND_COOLDOWN_SECONDS} segundos antes de solicitar otro código.',
            )
        return True, 'Puede solicitar nuevo código'
    except Exception as exc:
        logger.error('Error al verificar límites de reenvío: %s', exc, exc_info=True)
        return False, 'Error al verificar límites'


def increment_resend_count(user_id: str) -> None:
    """Incrementa el contador de reenvíos para un usuario."""
    try:
        resend_key = f'otp:resend_count:{user_id}'
        current_count = cache.get(resend_key, 0)
        cache.set(resend_key, current_count + 1, timeout=3600)
        cache.set(
            f'otp:resend_cooldown:{user_id}',
            True,
            timeout=settings.OTP_RESEND_COOLDOWN_SECONDS,
        )
    except Exception as exc:
        logger.error('Error al incrementar contador de reenvío: %s', exc, exc_info=True)


def cleanup_otp(user_id: str, session_token: str, purpose: str = 'LOGIN') -> None:
    """Elimina un OTP y sus datos relacionados de Redis."""
    try:
        cache.delete(f'otp:{purpose}:{user_id}')
        cache.delete(f'otp:{purpose}:{user_id}:session')
        cache.delete(f'otp:{purpose}:{user_id}:{session_token}')
        cache.delete(f'otp:attempts:{user_id}')
        cache.delete(f'otp:attempts:{user_id}:{session_token}')
        cache.delete(f'session:{session_token}')
    except Exception as exc:
        logger.error('Error al limpiar OTP: %s', exc, exc_info=True)

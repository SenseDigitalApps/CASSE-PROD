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
    """
    Genera un código OTP de 6 dígitos.
    
    Returns:
        str: Código OTP de 6 dígitos
    
    Example:
        >>> code = generate_otp_code()
        >>> print(code)  # "123456"
    """
    code = ''.join([str(secrets.randbelow(10)) for _ in range(settings.OTP_CODE_LENGTH)])
    return code


def generate_session_token() -> str:
    """
    Genera un token de sesión único para el flujo de OTP.
    
    Returns:
        str: UUID como string
    
    Example:
        >>> token = generate_session_token()
    """
    return str(uuid.uuid4())


def store_otp(user_id: str, session_token: str, otp_code: str, purpose: str = 'LOGIN') -> bool:
    """
    Almacena un código OTP en Redis con expiración.
    
    Args:
        user_id: ID del usuario (UUID como string)
        session_token: Token de sesión único
        otp_code: Código OTP
        purpose: Propósito del OTP (LOGIN, PASSWORD_RESET, etc.)
    
    Returns:
        bool: True si se almacenó correctamente
    
    Example:
        >>> store_otp(str(user.id), session_token, '123456', 'LOGIN')
    """
    try:
        # Clave para el OTP
        otp_key = f"otp:{purpose}:{user_id}:{session_token}"
        
        # Almacenar OTP con TTL en segundos
        ttl_seconds = settings.OTP_EXPIRATION_MINUTES * 60
        cache.set(otp_key, otp_code, timeout=ttl_seconds)
        
        # Almacenar session token -> user_id mapping
        session_key = f"session:{session_token}"
        cache.set(session_key, user_id, timeout=ttl_seconds)
        
        # Inicializar contador de intentos
        attempts_key = f"otp:attempts:{user_id}:{session_token}"
        cache.set(attempts_key, 0, timeout=ttl_seconds)
        
        logger.debug(f"OTP almacenado para usuario {user_id}, sesión {session_token}")
        return True
        
    except Exception as e:
        logger.error(f"Error al almacenar OTP: {e}", exc_info=True)
        return False


def get_otp(user_id: str, session_token: str, purpose: str = 'LOGIN') -> Optional[str]:
    """
    Obtiene un código OTP de Redis.
    
    Args:
        user_id: ID del usuario
        session_token: Token de sesión
        purpose: Propósito del OTP
    
    Returns:
        str: Código OTP si existe, None si no
    
    Example:
        >>> code = get_otp(str(user.id), session_token, 'LOGIN')
    """
    try:
        otp_key = f"otp:{purpose}:{user_id}:{session_token}"
        return cache.get(otp_key)
    except Exception as e:
        logger.error(f"Error al obtener OTP: {e}", exc_info=True)
        return None


def validate_otp(user_id: str, session_token: str, otp_code: str, purpose: str = 'LOGIN') -> Tuple[bool, str]:
    """
    Valida un código OTP.
    
    Args:
        user_id: ID del usuario
        session_token: Token de sesión
        otp_code: Código OTP a validar
        purpose: Propósito del OTP
    
    Returns:
        Tuple[bool, str]: (True/False, mensaje de error si falla)
    
    Example:
        >>> is_valid, message = validate_otp(str(user.id), session_token, '123456', 'LOGIN')
    """
    try:
        # Verificar intentos
        attempts_key = f"otp:attempts:{user_id}:{session_token}"
        attempts = cache.get(attempts_key, 0)
        
        if attempts >= settings.OTP_MAX_ATTEMPTS:
            return False, "Máximo número de intentos excedido. Solicita un nuevo código."
        
        # Obtener OTP almacenado
        stored_otp = get_otp(user_id, session_token, purpose)
        
        if not stored_otp:
            # Incrementar intentos
            cache.set(attempts_key, attempts + 1, timeout=settings.OTP_EXPIRATION_MINUTES * 60)
            return False, "Código OTP no encontrado o expirado. Solicita un nuevo código."
        
        # Validar código
        if stored_otp != otp_code:
            # Incrementar intentos
            cache.set(attempts_key, attempts + 1, timeout=settings.OTP_EXPIRATION_MINUTES * 60)
            remaining = settings.OTP_MAX_ATTEMPTS - (attempts + 1)
            return False, f"Código OTP incorrecto. Intentos restantes: {remaining}"
        
        # Código válido - eliminar OTP y contador
        otp_key = f"otp:{purpose}:{user_id}:{session_token}"
        cache.delete(otp_key)
        cache.delete(attempts_key)
        
        logger.info(f"OTP validado correctamente para usuario {user_id}")
        return True, "OTP válido"
        
    except Exception as e:
        logger.error(f"Error al validar OTP: {e}", exc_info=True)
        return False, "Error al validar código OTP"


def get_user_from_session_token(session_token: str) -> Optional[User]:
    """
    Obtiene el usuario desde un session token.
    
    Args:
        session_token: Token de sesión
    
    Returns:
        User: Usuario si el token es válido, None si no
    
    Example:
        >>> user = get_user_from_session_token(session_token)
    """
    try:
        session_key = f"session:{session_token}"
        user_id = cache.get(session_key)
        
        if not user_id:
            return None
        
        return User.objects.get(id=user_id)
        
    except User.DoesNotExist:
        logger.warning(f"Usuario no encontrado para session token {session_token}")
        return None
    except Exception as e:
        logger.error(f"Error al obtener usuario desde session token: {e}", exc_info=True)
        return None


def can_resend_otp(user_id: str) -> Tuple[bool, str]:
    """
    Verifica si el usuario puede solicitar un nuevo OTP.
    
    Args:
        user_id: ID del usuario
    
    Returns:
        Tuple[bool, str]: (True/False, mensaje de error si no puede)
    
    Example:
        >>> can_resend, message = can_resend_otp(str(user.id))
    """
    try:
        resend_key = f"otp:resend_count:{user_id}"
        resend_count = cache.get(resend_key, 0)
        
        if resend_count >= settings.OTP_MAX_RESEND_PER_HOUR:
            return False, f"Máximo de reenvíos alcanzado. Espera 1 hora antes de solicitar otro código."
        
        # Verificar cooldown
        cooldown_key = f"otp:resend_cooldown:{user_id}"
        if cache.get(cooldown_key):
            return False, f"Espera {settings.OTP_RESEND_COOLDOWN_SECONDS} segundos antes de solicitar otro código."
        
        return True, "Puede solicitar nuevo código"
        
    except Exception as e:
        logger.error(f"Error al verificar límites de reenvío: {e}", exc_info=True)
        return False, "Error al verificar límites"


def increment_resend_count(user_id: str) -> None:
    """
    Incrementa el contador de reenvíos para un usuario.
    
    Args:
        user_id: ID del usuario
    
    Example:
        >>> increment_resend_count(str(user.id))
    """
    try:
        resend_key = f"otp:resend_count:{user_id}"
        current_count = cache.get(resend_key, 0)
        cache.set(resend_key, current_count + 1, timeout=3600)  # 1 hora
        
        # Establecer cooldown
        cooldown_key = f"otp:resend_cooldown:{user_id}"
        cache.set(cooldown_key, True, timeout=settings.OTP_RESEND_COOLDOWN_SECONDS)
        
    except Exception as e:
        logger.error(f"Error al incrementar contador de reenvío: {e}", exc_info=True)


def cleanup_otp(user_id: str, session_token: str, purpose: str = 'LOGIN') -> None:
    """
    Elimina un OTP y sus datos relacionados de Redis.
    
    Args:
        user_id: ID del usuario
        session_token: Token de sesión
        purpose: Propósito del OTP
    
    Example:
        >>> cleanup_otp(str(user.id), session_token, 'LOGIN')
    """
    try:
        otp_key = f"otp:{purpose}:{user_id}:{session_token}"
        attempts_key = f"otp:attempts:{user_id}:{session_token}"
        session_key = f"session:{session_token}"
        
        cache.delete(otp_key)
        cache.delete(attempts_key)
        cache.delete(session_key)
        
    except Exception as e:
        logger.error(f"Error al limpiar OTP: {e}", exc_info=True)

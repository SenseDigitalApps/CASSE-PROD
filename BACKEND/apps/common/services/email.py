"""
Email service for sending emails.
"""
import logging
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def send_otp_email(user, otp_code: str, purpose: str = 'LOGIN') -> bool:
    """
    Envía un email con el código OTP al usuario.
    
    Args:
        user: Instancia del usuario
        otp_code: Código OTP de 6 dígitos
        purpose: Propósito del OTP (LOGIN, PASSWORD_RESET, etc.)
    
    Returns:
        bool: True si el email se envió correctamente, False en caso contrario
    
    Example:
        >>> from apps.common.services.email import send_otp_email
        >>> send_otp_email(user, '123456', 'LOGIN')
    """
    try:
        # Preparar contexto para el template
        context = {
            'user': user,
            'otp_code': otp_code,
            'purpose': purpose,
            'expiration_minutes': settings.OTP_EXPIRATION_MINUTES,
            'site_name': 'CASSE Seguros',
        }
        
        # Seleccionar template según el propósito
        if purpose == 'REGISTER':
            html_template = 'emails/otp_register.html'
            txt_template = 'emails/otp_register.txt'
        elif purpose == 'PASSWORD_RESET':
            html_template = 'emails/otp_password_reset.html'
            txt_template = 'emails/otp_password_reset.txt'
        else:
            html_template = 'emails/otp_login.html'
            txt_template = 'emails/otp_login.txt'
        
        # Renderizar templates
        try:
            html_message = render_to_string(html_template, context)
            plain_message = render_to_string(txt_template, context)
        except Exception as e:
            # Fallback: usar template de login si no existe el específico
            logger.warning(f"Template específico no encontrado, usando template de login: {e}")
            html_message = render_to_string('emails/otp_login.html', context)
            plain_message = strip_tags(html_message)
        
        # Determinar asunto según el propósito
        if purpose == 'LOGIN':
            subject = 'Código de verificación para iniciar sesión - CASSE Seguros'
        elif purpose == 'REGISTER':
            subject = 'Código de verificación para activar tu cuenta - CASSE Seguros'
        elif purpose == 'PASSWORD_RESET':
            subject = 'Código de verificación para restablecer contraseña - CASSE Seguros'
        else:
            subject = 'Código de verificación - CASSE Seguros'
        
        # Enviar email usando EmailMessage con conexión explícita
        from django.core.mail import EmailMessage, get_connection
        
        # Obtener conexión SMTP explícita para asegurar que use SMTP
        connection = get_connection(
            host=settings.EMAIL_HOST,
            port=settings.EMAIL_PORT,
            username=settings.EMAIL_HOST_USER,
            password=settings.EMAIL_HOST_PASSWORD,
            use_tls=settings.EMAIL_USE_TLS,
            use_ssl=settings.EMAIL_USE_SSL,
            timeout=getattr(settings, 'EMAIL_TIMEOUT', 30),
        )
        
        email = EmailMessage(
            subject=subject,
            body=html_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email_primary],
            connection=connection,
        )
        email.content_subtype = 'html'  # Indicar que es HTML
        
        # Enviar con captura de errores detallada
        try:
            email.send(fail_silently=False)
        except Exception as send_error:
            # Log detallado del error
            logger.error(f"Error detallado al enviar email: {send_error}", exc_info=True)
            # Re-lanzar el error para que se maneje arriba
            raise
        
        logger.info(f"Email OTP enviado a {user.email_primary} para propósito {purpose}")
        return True
        
    except Exception as e:
        logger.error(f"Error al enviar email OTP a {user.email_primary}: {e}", exc_info=True)
        return False

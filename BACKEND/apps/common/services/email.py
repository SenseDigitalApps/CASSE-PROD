"""
Email service for sending emails.
"""
import logging
from django.core.mail import send_mail, EmailMessage, get_connection
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def _send_html_email(*, subject: str, to_email: str, html_message: str, plain_message: str) -> bool:
    try:
        use_smtp = getattr(settings, 'USE_SMTP', False)
        if not use_smtp:
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[to_email],
                html_message=html_message,
                fail_silently=False,
            )
        else:
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
                to=[to_email],
                connection=connection,
            )
            email.content_subtype = 'html'
            email.send(fail_silently=False)
        return True
    except Exception as exc:
        logger.error('Error enviando email a %s: %s', to_email, exc, exc_info=True)
        return False


def send_otp_email(user, otp_code: str, purpose: str = 'LOGIN') -> bool:
    """
    Envía un email con el código OTP al usuario.
    """
    try:
        context = {
            'user': user,
            'otp_code': otp_code,
            'purpose': purpose,
            'expiration_minutes': settings.OTP_EXPIRATION_MINUTES,
            'site_name': 'CASSE Seguros',
        }

        if purpose == 'REGISTER':
            html_template = 'emails/otp_register.html'
            txt_template = 'emails/otp_register.txt'
        elif purpose == 'PASSWORD_RESET':
            html_template = 'emails/otp_password_reset.html'
            txt_template = 'emails/otp_password_reset.txt'
        else:
            html_template = 'emails/otp_login.html'
            txt_template = 'emails/otp_login.txt'

        try:
            html_message = render_to_string(html_template, context)
            plain_message = render_to_string(txt_template, context)
        except Exception as e:
            logger.warning(f"Template específico no encontrado, usando template de login: {e}")
            html_message = render_to_string('emails/otp_login.html', context)
            plain_message = strip_tags(html_message)

        if purpose == 'LOGIN':
            subject = 'Código de verificación para iniciar sesión - CASSE Seguros'
        elif purpose == 'REGISTER':
            subject = 'Código de verificación para activar tu cuenta - CASSE Seguros'
        elif purpose == 'PASSWORD_RESET':
            subject = 'Código de verificación para restablecer contraseña - CASSE Seguros'
        else:
            subject = 'Código de verificación - CASSE Seguros'

        ok = _send_html_email(
            subject=subject,
            to_email=user.email_primary,
            html_message=html_message,
            plain_message=plain_message,
        )
        if ok:
            logger.info(f"Email OTP enviado a {user.email_primary} para propósito {purpose}")
        return ok

    except Exception as e:
        logger.error(f"Error al enviar email OTP a {user.email_primary}: {e}", exc_info=True)
        return False


def send_quote_selected_emails(quote) -> tuple[bool, bool]:
    """
    Notify client and assigned commercial after "Lo quiero".

    Returns:
        (client_sent, commercial_sent)
    """
    product = quote.selected_product
    price = None
    currency = ''
    product_name = ''
    if product:
        product_name = product.product_name
        price = product.price_emission_local or product.price_emission
        currency = product.currency_local or product.currency or ''

    context = {
        'quote': quote,
        'user': quote.user,
        'product_name': product_name,
        'price': price,
        'currency': currency,
        'app_reference': quote.app_reference,
        'insurer_reference': quote.insurer_reference,
        'insurer_name': quote.display_insurer_name,
        'commercial_name': quote.assigned_commercial_name,
        'commercial_title': quote.assigned_commercial_title,
        'destination': quote.destination_siebel,
        'start_date': quote.start_date,
        'end_date': quote.end_date,
        'site_name': 'CASSE Seguros',
    }

    client_email = quote.contact_email or getattr(quote.user, 'email_primary', '')
    client_ok = False
    if client_email:
        try:
            html_message = render_to_string('emails/quote_selected_client.html', context)
            plain_message = render_to_string('emails/quote_selected_client.txt', context)
        except Exception:
            plain_message = (
                f'Cotización {quote.app_reference} recibida. '
                f'Un ejecutivo de CASSE Seguros te contactará en las próximas 24 horas hábiles.'
            )
            html_message = f'<p>{plain_message}</p>'
        client_ok = _send_html_email(
            subject=f'Cotización recibida {quote.app_reference} - CASSE Seguros',
            to_email=client_email,
            html_message=html_message,
            plain_message=plain_message,
        )

    commercial_email = quote.assigned_commercial_email
    commercial_ok = False
    if commercial_email:
        try:
            html_message = render_to_string('emails/quote_selected_commercial.html', context)
            plain_message = render_to_string('emails/quote_selected_commercial.txt', context)
        except Exception:
            plain_message = (
                f'Nueva cotización seleccionada {quote.app_reference}. '
                f'Cliente: {quote.contact_first_name} {quote.contact_last_name} '
                f'<{client_email}>.'
            )
            html_message = f'<p>{plain_message}</p>'
        commercial_ok = _send_html_email(
            subject=f'Nueva cotización {quote.app_reference} - CASSE Seguros',
            to_email=commercial_email,
            html_message=html_message,
            plain_message=plain_message,
        )

    return client_ok, commercial_ok

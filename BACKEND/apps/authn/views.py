"""
Views for authentication endpoints.
"""
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.views import TokenRefreshView

from .serializers import (
    LoginSerializer, 
    VerifyOTPSerializer, 
    ResendOTPSerializer,
    PasswordResetRequestSerializer,
    PasswordResetVerifyOTPSerializer
)
from apps.users.serializers import UserRegisterSerializer, UserPublicSerializer
from apps.users.services.users import register_user
from django.contrib.auth import get_user_model

User = get_user_model()
from apps.authn.services.jwt import generate_tokens_for_user
from apps.authn.services.otp import (
    generate_otp_code,
    generate_session_token,
    store_otp,
    validate_otp,
    get_user_from_session_token,
    can_resend_otp,
    increment_resend_count,
    cleanup_otp
)
from apps.common.services.email import send_otp_email
from apps.audit.services.audit_log import log_audit_event
from apps.audit.constants import (
    LOGIN_SUCCESS, LOGIN_FAILED, OTP_SENT, OTP_VERIFIED, 
    OTP_FAILED, OTP_EXPIRED, OTP_RESENT, USER_REGISTERED, USER_ACTIVATED,
    PASSWORD_RESET_REQUESTED, PASSWORD_RESET_COMPLETED, PASSWORD_RESET_FAILED,
    USER_REACTIVATED
)
from django.db import IntegrityError

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """
    Obtiene la IP del cliente desde el request.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


class LoginView(APIView):
    """
    View for user login (Step 1: validates credentials and generates OTP).
    POST /api/v1/auth/login/
    
    Rate limited: 5 attempts per minute to prevent brute force attacks.
    
    Returns:
        - session_token: Token temporal para verificar OTP
        - expires_in: Tiempo de expiración en segundos (20 minutos = 1200 segundos)
        - message: Mensaje informativo
    """
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer
    throttle_classes = [AnonRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        """
        Handle user login - Step 1: Generate OTP.
        """
        serializer = LoginSerializer(data=request.data)
        ip_address = get_client_ip(request)
        
        if not serializer.is_valid():
            # Intentar obtener email para audit log
            email = request.data.get('email_primary', '')
            if email:
                log_audit_event(
                    actor_user=None,
                    action=LOGIN_FAILED,
                    entity='User',
                    entity_id=None,
                    metadata={'email': email, 'reason': 'invalid_credentials'},
                    ip_address=ip_address
                )
            
            return Response(
                serializer.errors,
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Usuario validado en el serializer
        user = serializer.validated_data['user']
        
        # Verificar que el usuario no esté eliminado (doble verificación)
        if user.status == user.Status.DELETED:
            log_audit_event(
                actor_user=user,
                action=LOGIN_FAILED,
                entity='User',
                entity_id=user.id,
                metadata={'reason': 'account_deleted'},
                ip_address=ip_address
            )
            return Response(
                {'detail': 'Cuenta eliminada. Contacta a soporte si deseas reactivarla.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Verificar que el usuario esté activo
        if user.status != user.Status.ACTIVE:
            log_audit_event(
                actor_user=user,
                action=LOGIN_FAILED,
                entity='User',
                entity_id=user.id,
                metadata={'reason': 'user_suspended'},
                ip_address=ip_address
            )
            return Response(
                {'detail': 'Usuario suspendido'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Generar OTP y session token
        try:
            otp_code = generate_otp_code()
            session_token = generate_session_token()
            
            # Almacenar OTP en Redis
            if not store_otp(str(user.id), session_token, otp_code, purpose='LOGIN'):
                logger.error(f"Error al almacenar OTP para usuario {user.id}")
                return Response(
                    {'detail': 'Error al generar código de verificación'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # Enviar email con OTP
            if not send_otp_email(user, otp_code, purpose='LOGIN'):
                logger.error(f"Error al enviar email OTP a {user.email_primary}")
                # Limpiar OTP si falla el envío
                cleanup_otp(str(user.id), session_token, purpose='LOGIN')
                return Response(
                    {'detail': 'Error al enviar código de verificación por email'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # Audit log
            log_audit_event(
                actor_user=user,
                action=OTP_SENT,
                entity='User',
                entity_id=user.id,
                metadata={'email': user.email_primary, 'purpose': 'LOGIN'},
                ip_address=ip_address
            )
            
            from django.conf import settings
            expires_in = settings.OTP_EXPIRATION_MINUTES * 60
            
            return Response({
                'session_token': session_token,
                'expires_in': expires_in,
                'message': f'Código de verificación enviado a {user.email_primary}. El código expira en {settings.OTP_EXPIRATION_MINUTES} minutos.'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error en proceso de login OTP para usuario {user.id}: {e}", exc_info=True)
            return Response(
                {'detail': 'Error al procesar solicitud de login'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RegisterView(APIView):
    """
    View for user registration (Step 1: creates user and generates OTP).
    POST /api/v1/auth/register/
    
    Creates user in SUSPENDED status, sends OTP via email.
    User must verify OTP to activate account.
    
    Returns:
        - session_token: Token temporal para verificar OTP
        - expires_in: Tiempo de expiración en segundos (20 minutos = 1200 segundos)
        - message: Mensaje informativo
    """
    permission_classes = [AllowAny]
    serializer_class = UserRegisterSerializer

    def post(self, request):
        """
        Handle user registration - Step 1: Create user and generate OTP.
        Also handles reactivation of DELETED users.
        """
        serializer = UserRegisterSerializer(data=request.data)
        ip_address = get_client_ip(request)
        
        # Verificar si hay usuario DELETED antes de validar serializer
        # Esto permite manejar el caso de reactivación incluso si el serializer falla por unique_together
        email_primary = request.data.get('email_primary', '').strip().lower()
        id_type = request.data.get('id_type')
        id_number = request.data.get('id_number')
        
        existing_user = None
        if email_primary:
            existing_user = User.objects.filter(
                email_primary=email_primary,
                status=User.Status.DELETED
            ).first()
        
        if not existing_user and id_type and id_number:
            existing_user = User.objects.filter(
                id_type=id_type,
                id_number=id_number,
                status=User.Status.DELETED
            ).first()
        
        # Si hay usuario DELETED, validar manualmente los datos sin usar el serializer completo
        # para evitar el error de unique_together
        if existing_user:
            # Validar datos manualmente
            try:
                from django.contrib.auth.password_validation import validate_password
                password = request.data.get('password')
                if password:
                    validate_password(password)
            except Exception as e:
                return Response(
                    {'password': [str(e)]},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Si hay usuario DELETED, proceder con reactivación directamente
            # (saltar validación de serializer que fallaría por unique_together)
            validated_data = {
                'full_name': request.data.get('full_name'),
                'id_type': request.data.get('id_type'),
                'id_number': request.data.get('id_number'),
                'email_primary': email_primary,
                'phone': request.data.get('phone'),
                'birth_date': request.data.get('birth_date'),
                'email_secondary': request.data.get('email_secondary'),
                'address': request.data.get('address'),
                'profile_photo_url': request.data.get('profile_photo_url'),
            }
            password = request.data.get('password')
        else:
            # Validar con serializer normal si no hay usuario DELETED
            if not serializer.is_valid():
                return Response(
                    serializer.errors,
                    status=status.HTTP_400_BAD_REQUEST
                )
            validated_data = serializer.validated_data.copy()
            password = validated_data.pop('password')
            email_primary = validated_data.get('email_primary').strip().lower()
            id_type = validated_data.get('id_type')
            id_number = validated_data.get('id_number')
            existing_user = None
        
        try:
            # Determinar si es reactivación
            is_reactivation = existing_user is not None
            
            if is_reactivation:
                # REACTIVAR USUARIO ELIMINADO
                user = existing_user
                
                # Actualizar todos los campos del formulario
                for field, value in validated_data.items():
                    if hasattr(user, field):
                        setattr(user, field, value)
                
                # Cambiar contraseña a la nueva
                user.set_password(password)
                
                # Reactivar: cambiar status y limpiar deleted_at
                user.status = User.Status.SUSPENDED
                user.deleted_at = None
                
                # Guardar cambios
                user.save()
                
                # Audit log de reactivación
                log_audit_event(
                    actor_user=user,
                    action=USER_REACTIVATED,
                    entity='User',
                    entity_id=user.id,
                    metadata={
                        'email': user.email_primary,
                        'reactivated_from': 'DELETED',
                        'pending_otp_verification': True
                    },
                    ip_address=ip_address
                )
            else:
                # CREAR NUEVO USUARIO
                validated_data.setdefault('role', User.Role.CLIENT)
                validated_data.setdefault('status', User.Status.SUSPENDED)
                
                user = User.objects.create_user(
                    email_primary=validated_data.pop('email_primary'),
                    password=password,
                    **validated_data
                )
                
                # Audit log de registro nuevo
                log_audit_event(
                    actor_user=user,
                    action=USER_REGISTERED,
                    entity='User',
                    entity_id=user.id,
                    metadata={
                        'email': user.email_primary,
                        'role': user.role,
                        'status': 'SUSPENDED',
                        'pending_otp_verification': True
                    },
                    ip_address=ip_address
                )
            
            # Generar OTP y session token (común para ambos casos)
            otp_code = generate_otp_code()
            session_token = generate_session_token()
            
            # Almacenar OTP en Redis
            if not store_otp(str(user.id), session_token, otp_code, purpose='REGISTER'):
                logger.error(f"Error al almacenar OTP para usuario {user.id}")
                # Solo eliminar si era un usuario nuevo (no reactivado)
                if not is_reactivation:
                    user.delete()
                return Response(
                    {'detail': 'Error al generar código de verificación'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # Enviar email con OTP
            if not send_otp_email(user, otp_code, purpose='REGISTER'):
                logger.error(f"Error al enviar email OTP a {user.email_primary}")
                cleanup_otp(str(user.id), session_token, purpose='REGISTER')
                # Solo eliminar si era un usuario nuevo (no reactivado)
                if not is_reactivation:
                    user.delete()
                return Response(
                    {'detail': 'Error al enviar código de verificación por email'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # Audit log OTP enviado (común para ambos casos)
            log_audit_event(
                actor_user=user,
                action=OTP_SENT,
                entity='User',
                entity_id=user.id,
                metadata={'email': user.email_primary, 'purpose': 'REGISTER'},
                ip_address=ip_address
            )
            
            from django.conf import settings
            expires_in = settings.OTP_EXPIRATION_MINUTES * 60
            
            # Mismo mensaje para registro nuevo y reactivación
            return Response({
                'session_token': session_token,
                'expires_in': expires_in,
                'message': f'Usuario registrado. Código de verificación enviado a {user.email_primary}. El código expira en {settings.OTP_EXPIRATION_MINUTES} minutos.'
            }, status=status.HTTP_201_CREATED)
            
        except IntegrityError as e:
            logger.error(f"Error de integridad al registrar usuario: {e}")
            
            # Verificar si el error es por usuario DELETED que necesita reactivación
            error_str = str(e).lower()
            if 'unique' in error_str or 'duplicate' in error_str:
                # Intentar encontrar usuario DELETED con estos datos
                try:
                    existing_user = User.objects.filter(
                        email_primary=email_primary,
                        status=User.Status.DELETED
                    ).first()
                    
                    if not existing_user:
                        existing_user = User.objects.filter(
                            id_type=id_type,
                            id_number=id_number,
                            status=User.Status.DELETED
                        ).first()
                    
                    if existing_user:
                        # Reactivar usuario DELETED
                        user = existing_user
                        
                        # Actualizar todos los campos del formulario
                        for field, value in validated_data.items():
                            if hasattr(user, field):
                                setattr(user, field, value)
                        
                        # Cambiar contraseña a la nueva
                        user.set_password(password)
                        
                        # Reactivar: cambiar status y limpiar deleted_at
                        user.status = User.Status.SUSPENDED
                        user.deleted_at = None
                        
                        # Guardar cambios
                        user.save()
                        
                        # Continuar con el flujo de OTP (saltar al código común)
                        # Generar OTP y session token
                        otp_code = generate_otp_code()
                        session_token = generate_session_token()
                        
                        # Almacenar OTP en Redis
                        if not store_otp(str(user.id), session_token, otp_code, purpose='REGISTER'):
                            logger.error(f"Error al almacenar OTP para usuario {user.id}")
                            return Response(
                                {'detail': 'Error al generar código de verificación'},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR
                            )
                        
                        # Enviar email con OTP
                        if not send_otp_email(user, otp_code, purpose='REGISTER'):
                            logger.error(f"Error al enviar email OTP a {user.email_primary}")
                            cleanup_otp(str(user.id), session_token, purpose='REGISTER')
                            return Response(
                                {'detail': 'Error al enviar código de verificación por email'},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR
                            )
                        
                        # Audit log de reactivación
                        log_audit_event(
                            actor_user=user,
                            action=USER_REACTIVATED,
                            entity='User',
                            entity_id=user.id,
                            metadata={
                                'email': user.email_primary,
                                'reactivated_from': 'DELETED',
                                'pending_otp_verification': True
                            },
                            ip_address=ip_address
                        )
                        
                        log_audit_event(
                            actor_user=user,
                            action=OTP_SENT,
                            entity='User',
                            entity_id=user.id,
                            metadata={'email': user.email_primary, 'purpose': 'REGISTER'},
                            ip_address=ip_address
                        )
                        
                        from django.conf import settings
                        expires_in = settings.OTP_EXPIRATION_MINUTES * 60
                        
                        return Response({
                            'session_token': session_token,
                            'expires_in': expires_in,
                            'message': f'Usuario registrado. Código de verificación enviado a {user.email_primary}. El código expira en {settings.OTP_EXPIRATION_MINUTES} minutos.'
                        }, status=status.HTTP_201_CREATED)
                except Exception as reactivation_error:
                    logger.error(f"Error al intentar reactivar usuario: {reactivation_error}", exc_info=True)
            
            return Response(
                {'detail': 'Error al procesar registro. Verifica que los datos sean únicos.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error al registrar usuario: {e}", exc_info=True)
            return Response(
                {'detail': 'Error al procesar solicitud de registro'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class VerifyOTPView(APIView):
    """
    View for OTP verification (Step 2: validates OTP and generates JWT tokens).
    POST /api/v1/auth/verify-otp/
    
    Supports both LOGIN and REGISTER purposes.
    For REGISTER: activates user account.
    For LOGIN: generates tokens for existing active user.
    
    Rate limited: 5 attempts per minute to prevent brute force attacks.
    """
    permission_classes = [AllowAny]
    serializer_class = VerifyOTPSerializer
    throttle_classes = [AnonRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        """
        Handle OTP verification and generate JWT tokens.
        """
        serializer = VerifyOTPSerializer(data=request.data)
        ip_address = get_client_ip(request)
        
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        session_token = serializer.validated_data['session_token']
        otp_code = serializer.validated_data['otp_code']
        
        # Obtener usuario desde session token
        user = get_user_from_session_token(session_token)
        
        if not user:
            log_audit_event(
                actor_user=None,
                action=OTP_FAILED,
                entity='User',
                entity_id=None,
                metadata={'reason': 'invalid_session_token'},
                ip_address=ip_address
            )
            return Response(
                {'detail': 'Token de sesión inválido o expirado'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Determinar propósito: si el usuario está SUSPENDED, es REGISTER; si está ACTIVE, es LOGIN
        purpose = 'REGISTER' if user.status == User.Status.SUSPENDED else 'LOGIN'
        
        # Validar OTP
        is_valid, message = validate_otp(str(user.id), session_token, otp_code, purpose=purpose)
        
        if not is_valid:
            log_audit_event(
                actor_user=user,
                action=OTP_FAILED,
                entity='User',
                entity_id=user.id,
                metadata={'email': user.email_primary, 'purpose': purpose, 'reason': message},
                ip_address=ip_address
            )
            return Response(
                {'detail': message},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # OTP válido
        # Si es REGISTER, activar usuario
        if purpose == 'REGISTER':
            if user.status == User.Status.SUSPENDED:
                user.status = User.Status.ACTIVE
                user.save(update_fields=['status'])
                
                # Audit log de activación
                log_audit_event(
                    actor_user=user,
                    action=USER_ACTIVATED,
                    entity='User',
                    entity_id=user.id,
                    metadata={
                        'email': user.email_primary,
                        'activated_by': 'OTP_VERIFICATION',
                        'registration_verified': True
                    },
                    ip_address=ip_address
                )
        
        # Generar tokens JWT
        try:
            tokens = generate_tokens_for_user(user)
        except Exception as e:
            logger.error(f"Error al generar tokens para usuario {user.id}: {e}", exc_info=True)
            return Response(
                {'detail': 'Error al generar tokens'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Actualizar last_login_at
        from django.utils import timezone
        user.last_login_at = timezone.now()
        user.save(update_fields=['last_login_at'])
        
        # Limpiar datos de OTP
        cleanup_otp(str(user.id), session_token, purpose=purpose)
        
        # Audit log
        log_audit_event(
            actor_user=user,
            action=OTP_VERIFIED,
            entity='User',
            entity_id=user.id,
            metadata={'email': user.email_primary, 'purpose': purpose},
            ip_address=ip_address
        )
        
        if purpose == 'LOGIN':
            log_audit_event(
                actor_user=user,
                action=LOGIN_SUCCESS,
                entity='User',
                entity_id=user.id,
                metadata={'email': user.email_primary},
                ip_address=ip_address
            )
        
        # Serializar datos del usuario
        user_data = UserPublicSerializer(user, context={'request': request}).data
        
        return Response({
            'access': tokens['access'],
            'refresh': tokens['refresh'],
            'user': user_data
        }, status=status.HTTP_200_OK)


class ResendOTPView(APIView):
    """
    View for resending OTP code.
    POST /api/v1/auth/resend-otp/
    
    Rate limited: 3 resends per hour per user.
    """
    permission_classes = [AllowAny]
    serializer_class = ResendOTPSerializer
    throttle_classes = [AnonRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        """
        Handle OTP resend request.
        """
        serializer = ResendOTPSerializer(data=request.data)
        ip_address = get_client_ip(request)
        
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        session_token = serializer.validated_data['session_token']
        
        # Obtener usuario desde session token
        user = get_user_from_session_token(session_token)
        
        if not user:
            return Response(
                {'detail': 'Token de sesión inválido o expirado'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Determinar propósito: si el usuario está SUSPENDED, es REGISTER; si está ACTIVE, es LOGIN
        purpose = 'REGISTER' if user.status == User.Status.SUSPENDED else 'LOGIN'
        
        # Verificar límites de reenvío
        can_resend, message = can_resend_otp(str(user.id))
        
        if not can_resend:
            return Response(
                {'detail': message},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
        
        # Generar nuevo OTP
        try:
            otp_code = generate_otp_code()
            
            # Limpiar OTP anterior si existe
            cleanup_otp(str(user.id), session_token, purpose=purpose)
            
            # Almacenar nuevo OTP
            if not store_otp(str(user.id), session_token, otp_code, purpose=purpose):
                logger.error(f"Error al almacenar nuevo OTP para usuario {user.id}")
                return Response(
                    {'detail': 'Error al generar código de verificación'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # Enviar email con nuevo OTP
            if not send_otp_email(user, otp_code, purpose=purpose):
                logger.error(f"Error al enviar email OTP a {user.email_primary}")
                cleanup_otp(str(user.id), session_token, purpose=purpose)
                return Response(
                    {'detail': 'Error al enviar código de verificación por email'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # Incrementar contador de reenvíos
            increment_resend_count(str(user.id))
            
            # Audit log
            log_audit_event(
                actor_user=user,
                action=OTP_RESENT,
                entity='User',
                entity_id=user.id,
                metadata={'email': user.email_primary, 'purpose': purpose},
                ip_address=ip_address
            )
            
            from django.conf import settings
            expires_in = settings.OTP_EXPIRATION_MINUTES * 60
            
            return Response({
                'session_token': session_token,
                'expires_in': expires_in,
                'message': f'Nuevo código de verificación enviado a {user.email_primary}. El código expira en {settings.OTP_EXPIRATION_MINUTES} minutos.'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error al reenviar OTP para usuario {user.id}: {e}", exc_info=True)
            return Response(
                {'detail': 'Error al procesar solicitud de reenvío'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PasswordResetRequestView(APIView):
    """
    View for requesting password reset (Step 1: generates OTP).
    POST /api/v1/auth/password-reset/request/
    
    Rate limited: 5 attempts per minute to prevent abuse.
    
    Returns:
        - session_token: Token temporal para verificar OTP
        - expires_in: Tiempo de expiración en segundos (20 minutos = 1200 segundos)
        - message: Mensaje informativo
    """
    permission_classes = [AllowAny]
    serializer_class = PasswordResetRequestSerializer
    throttle_classes = [AnonRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        """
        Handle password reset request - Step 1: Generate OTP.
        """
        serializer = PasswordResetRequestSerializer(data=request.data)
        ip_address = get_client_ip(request)
        
        if not serializer.is_valid():
            # No revelar si el email existe o no por seguridad
            return Response(
                {'detail': 'Si el email existe, recibirás un código de verificación'},
                status=status.HTTP_200_OK  # Retornar 200 para no revelar información
            )
        
        # Usuario validado en el serializer
        user = serializer.validated_data['user']
        
        # Generar OTP y session token
        try:
            otp_code = generate_otp_code()
            session_token = generate_session_token()
            
            # Almacenar OTP en Redis
            if not store_otp(str(user.id), session_token, otp_code, purpose='PASSWORD_RESET'):
                logger.error(f"Error al almacenar OTP para recuperación de contraseña del usuario {user.id}")
                return Response(
                    {'detail': 'Si el email existe, recibirás un código de verificación'},
                    status=status.HTTP_200_OK
                )
            
            # Enviar email con OTP
            if not send_otp_email(user, otp_code, purpose='PASSWORD_RESET'):
                logger.error(f"Error al enviar email OTP para recuperación de contraseña a {user.email_primary}")
                # Limpiar OTP si falla el envío
                cleanup_otp(str(user.id), session_token, purpose='PASSWORD_RESET')
                return Response(
                    {'detail': 'Si el email existe, recibirás un código de verificación'},
                    status=status.HTTP_200_OK
                )
            
            # Audit log
            log_audit_event(
                actor_user=user,
                action=PASSWORD_RESET_REQUESTED,
                entity='User',
                entity_id=user.id,
                metadata={'email': user.email_primary},
                ip_address=ip_address
            )
            
            log_audit_event(
                actor_user=user,
                action=OTP_SENT,
                entity='User',
                entity_id=user.id,
                metadata={'email': user.email_primary, 'purpose': 'PASSWORD_RESET'},
                ip_address=ip_address
            )
            
            from django.conf import settings
            expires_in = settings.OTP_EXPIRATION_MINUTES * 60
            
            return Response({
                'session_token': session_token,
                'expires_in': expires_in,
                'message': f'Si el email existe, recibirás un código de verificación. El código expira en {settings.OTP_EXPIRATION_MINUTES} minutos.'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error en proceso de recuperación de contraseña para usuario {user.id}: {e}", exc_info=True)
            return Response(
                {'detail': 'Si el email existe, recibirás un código de verificación'},
                status=status.HTTP_200_OK
            )


class PasswordResetVerifyOTPView(APIView):
    """
    View for password reset OTP verification (Step 2: validates OTP and sets new password).
    POST /api/v1/auth/password-reset/verify/
    
    Rate limited: 5 attempts per minute to prevent brute force attacks.
    """
    permission_classes = [AllowAny]
    serializer_class = PasswordResetVerifyOTPSerializer
    throttle_classes = [AnonRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        """
        Handle password reset OTP verification and set new password.
        """
        serializer = PasswordResetVerifyOTPSerializer(data=request.data)
        ip_address = get_client_ip(request)
        
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        session_token = serializer.validated_data['session_token']
        otp_code = serializer.validated_data['otp_code']
        new_password = serializer.validated_data['new_password']
        
        # Obtener usuario desde session token
        user = get_user_from_session_token(session_token)
        
        if not user:
            log_audit_event(
                actor_user=None,
                action=PASSWORD_RESET_FAILED,
                entity='User',
                entity_id=None,
                metadata={'reason': 'invalid_session_token'},
                ip_address=ip_address
            )
            return Response(
                {'detail': 'Token de sesión inválido o expirado'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Validar OTP
        is_valid, message = validate_otp(str(user.id), session_token, otp_code, purpose='PASSWORD_RESET')
        
        if not is_valid:
            log_audit_event(
                actor_user=user,
                action=PASSWORD_RESET_FAILED,
                entity='User',
                entity_id=user.id,
                metadata={'email': user.email_primary, 'reason': message},
                ip_address=ip_address
            )
            return Response(
                {'detail': message},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # OTP válido - cambiar contraseña
        try:
            user.set_password(new_password)
            user.save(update_fields=['password'])
            
            # Limpiar datos de OTP
            cleanup_otp(str(user.id), session_token, purpose='PASSWORD_RESET')
            
            # Audit log
            log_audit_event(
                actor_user=user,
                action=PASSWORD_RESET_COMPLETED,
                entity='User',
                entity_id=user.id,
                metadata={'email': user.email_primary},
                ip_address=ip_address
            )
            
            logger.info(f"Contraseña restablecida exitosamente para usuario {user.email_primary}")
            
            return Response({
                'message': 'Contraseña restablecida correctamente'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error al restablecer contraseña para usuario {user.id}: {e}", exc_info=True)
            log_audit_event(
                actor_user=user,
                action=PASSWORD_RESET_FAILED,
                entity='User',
                entity_id=user.id,
                metadata={'email': user.email_primary, 'reason': 'error_updating_password'},
                ip_address=ip_address
            )
            return Response(
                {'detail': 'Error al restablecer contraseña'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RefreshTokenView(TokenRefreshView):
    """
    View for refreshing JWT access token.
    POST /api/v1/auth/jwt/refresh/
    
    Uses rest_framework_simplejwt's TokenRefreshView.
    """
    permission_classes = [AllowAny]


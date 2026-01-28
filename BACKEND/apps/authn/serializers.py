"""
Serializers for authentication.
"""
from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class LoginSerializer(serializers.Serializer):
    """
    Serializer for user login (Step 1: validates credentials and generates OTP).
    """
    email_primary = serializers.EmailField(required=True)
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )

    def validate(self, attrs):
        """
        Validate user credentials.
        """
        email = attrs.get('email_primary')
        password = attrs.get('password')

        if not email or not password:
            raise serializers.ValidationError(
                'Debe proporcionar email y contraseña'
            )

        # Normalizar email
        email = email.strip().lower()

        try:
            # Obtener usuario por email
            user = User.objects.get(email_primary=email)
        except User.DoesNotExist:
            raise serializers.ValidationError('Credenciales inválidas')

        # Verificar contraseña
        if not user.check_password(password):
            raise serializers.ValidationError('Credenciales inválidas')

        # Verificar que el usuario esté activo
        if user.status == User.Status.DELETED:
            raise serializers.ValidationError('Cuenta eliminada. Contacta a soporte si deseas reactivarla.')
        
        if user.status != User.Status.ACTIVE:
            raise serializers.ValidationError('Usuario suspendido')

        attrs['user'] = user
        return attrs


class VerifyOTPSerializer(serializers.Serializer):
    """
    Serializer for OTP verification (Step 2: validates OTP and generates JWT tokens).
    """
    session_token = serializers.CharField(required=True, help_text="Token de sesión recibido en el paso 1")
    otp_code = serializers.CharField(
        required=True,
        min_length=6,
        max_length=6,
        help_text="Código OTP de 6 dígitos recibido por email"
    )

    def validate_otp_code(self, value):
        """
        Validar que el código OTP solo contenga dígitos.
        """
        if not value.isdigit():
            raise serializers.ValidationError('El código OTP debe contener solo números')
        return value


class ResendOTPSerializer(serializers.Serializer):
    """
    Serializer for requesting OTP resend.
    """
    session_token = serializers.CharField(required=True, help_text="Token de sesión recibido en el paso 1")


class PasswordResetRequestSerializer(serializers.Serializer):
    """
    Serializer for requesting password reset (Step 1: generates OTP).
    """
    email_primary = serializers.EmailField(required=True, help_text="Email del usuario que solicita recuperación de contraseña")

    def validate(self, attrs):
        """
        Validate that user exists and is active.
        """
        email = attrs.get('email_primary')
        
        if not email:
            raise serializers.ValidationError('Debe proporcionar un email')
        
        # Normalizar email
        email = email.strip().lower()
        
        try:
            user = User.objects.get(email_primary=email)
        except User.DoesNotExist:
            # No revelar si el email existe o no por seguridad
            raise serializers.ValidationError('Si el email existe, recibirás un código de verificación')
        
        # Verificar que el usuario no esté eliminado
        if user.status == User.Status.DELETED:
            raise serializers.ValidationError('Si el email existe, recibirás un código de verificación')
        
        # Verificar que el usuario esté activo o suspendido (no eliminado)
        if user.status not in [User.Status.ACTIVE, User.Status.SUSPENDED]:
            raise serializers.ValidationError('Si el email existe, recibirás un código de verificación')
        
        attrs['user'] = user
        return attrs


class PasswordResetVerifyOTPSerializer(serializers.Serializer):
    """
    Serializer for password reset OTP verification (Step 2: validates OTP and sets new password).
    """
    session_token = serializers.CharField(required=True, help_text="Token de sesión recibido en el paso 1")
    otp_code = serializers.CharField(
        required=True,
        min_length=6,
        max_length=6,
        help_text="Código OTP de 6 dígitos recibido por email"
    )
    new_password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={'input_type': 'password'},
        help_text="Nueva contraseña que debe cumplir las políticas de seguridad"
    )

    def validate_otp_code(self, value):
        """
        Validar que el código OTP solo contenga dígitos.
        """
        if not value.isdigit():
            raise serializers.ValidationError('El código OTP debe contener solo números')
        return value


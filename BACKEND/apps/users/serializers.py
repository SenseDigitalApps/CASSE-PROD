"""
Serializers for User model.
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class UserPublicSerializer(serializers.ModelSerializer):
    """
    Serializer for public user data.
    Adjusts fields based on the requesting user's role.
    """
    
    class Meta:
        model = User
        fields = [
            'id',
            'full_name',
            'email_primary',
            'phone',
            'email_secondary',
            'role',
            'status',
            'profile_photo_url',
            'created_at',
            'updated_at',
            'last_login_at',
        ]
        read_only_fields = [
            'id',
            'email_primary',
            'role',
            'status',
            'created_at',
            'updated_at',
            'last_login_at',
        ]

    def to_representation(self, instance):
        """
        Adjust fields based on the requesting user's role.
        """
        representation = super().to_representation(instance)
        
        # Obtener el usuario que hace la petición (si está disponible)
        request = self.context.get('request')
        requesting_user = getattr(request, 'user', None) if request else None
        
        # Verificar si el usuario está autenticado (no es AnonymousUser)
        is_authenticated = requesting_user and requesting_user.is_authenticated
        
        # Si no hay usuario autenticado o es CLIENT, ocultar datos sensibles
        if not is_authenticated or requesting_user.role == User.Role.CLIENT:
            # Solo mostrar datos básicos para clientes
            if is_authenticated and requesting_user.id == instance.id:
                # Si es el propio usuario, mostrar más campos
                pass  # Mostrar todos los campos definidos
            else:
                # Si es otro usuario o no autenticado, ocultar datos sensibles
                representation.pop('email_secondary', None)
                representation.pop('phone', None)
        
        # Para ADMIN, SUPERVISOR, INTERVENTORIA mostrar todos los campos
        # (ya están incluidos en fields)
        
        return representation


class UserRegisterSerializer(serializers.ModelSerializer):
    """
    Serializer for user registration (self-registration).
    """
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={'input_type': 'password'}
    )

    class Meta:
        model = User
        fields = [
            'full_name',
            'id_type',
            'id_number',
            'email_primary',
            'phone',
            'birth_date',
            'password',
            'email_secondary',
            'address',
            'profile_photo_url',
        ]
        extra_kwargs = {
            'full_name': {'required': True},
            'id_type': {'required': True},
            'id_number': {'required': True},
            'email_primary': {
                'required': True,
                # Deshabilitar validación automática de unicidad
                # La validamos manualmente en validate_email_primary()
                'validators': []
            },
            'phone': {'required': True},
            'birth_date': {'required': True},
            'email_secondary': {'required': False, 'allow_blank': True},
            'address': {'required': False, 'allow_blank': True},
            'profile_photo_url': {'required': False, 'allow_blank': True},
        }
    
    def __init__(self, *args, **kwargs):
        """
        Deshabilitar validación automática de unique_together.
        La validamos manualmente en validate().
        """
        super().__init__(*args, **kwargs)
        # Remover validadores de unique_together
        if hasattr(self, 'fields'):
            # No hay forma directa de deshabilitar unique_together en DRF
            # Lo manejamos en validate() y capturamos IntegrityError
            pass

    def validate_email_primary(self, value):
        """
        Validate that email is unique, but allow if user is DELETED (will be reactivated).
        """
        value = value.strip().lower()
        existing_user = User.objects.filter(email_primary=value).first()
        
        if existing_user:
            # Si el usuario existe y NO está eliminado, rechazar
            if existing_user.status != User.Status.DELETED:
                raise serializers.ValidationError('Este email ya está en uso')
            # Si está DELETED, permitir (se reactivará en la vista)
        
        return value

    def validate(self, attrs):
        """
        Validate that id_type + id_number combination is unique, but allow if user is DELETED.
        """
        email = attrs.get('email_primary', '').strip().lower()
        id_type = attrs.get('id_type')
        id_number = attrs.get('id_number')
        
        # Validar combinación id_type + id_number
        existing_by_id = User.objects.filter(
            id_type=id_type,
            id_number=id_number
        ).first()
        
        if existing_by_id:
            # Si existe y NO está eliminado, rechazar
            if existing_by_id.status != User.Status.DELETED:
                raise serializers.ValidationError({
                    'id_number': 'Esta identificación ya está registrada'
                })
            # Si está DELETED pero el email es diferente, rechazar
            # (misma persona, email diferente = inconsistencia)
            if existing_by_id.email_primary.lower() != email:
                raise serializers.ValidationError({
                    'id_number': 'Esta identificación ya está registrada con otro email'
                })
        
        return attrs
    
    def run_validation(self, data=None):
        """
        Override to catch unique_together validation errors and check if user is DELETED.
        """
        try:
            return super().run_validation(data)
        except serializers.ValidationError as e:
            # Si el error es de unique_together, verificar si el usuario está DELETED
            if hasattr(e, 'detail') and isinstance(e.detail, dict):
                non_field_errors = e.detail.get('non_field_errors', [])
                if non_field_errors:
                    error_str = str(non_field_errors[0]).lower()
                    if 'id_type' in error_str and 'id_number' in error_str and ('único' in error_str or 'unique' in error_str):
                        # Intentar obtener los datos para verificar si el usuario está DELETED
                        try:
                            if isinstance(data, dict):
                                email = data.get('email_primary', '').strip().lower()
                                id_type = data.get('id_type')
                                id_number = data.get('id_number')
                                
                                if id_type and id_number:
                                    existing_user = User.objects.filter(
                                        id_type=id_type,
                                        id_number=id_number
                                    ).first()
                                    
                                    if existing_user and existing_user.status == User.Status.DELETED:
                                        # Si el usuario está DELETED, permitir (se reactivará en la vista)
                                        # Verificar que el email coincida
                                        if email and existing_user.email_primary.lower() != email:
                                            raise serializers.ValidationError({
                                                'id_number': 'Esta identificación ya está registrada con otro email'
                                            })
                                        # Si todo está bien, continuar sin error de unique_together
                                        # Necesitamos ejecutar la validación pero ignorar el error de unique_together
                                        # Para esto, ejecutamos la validación manualmente sin el unique_together
                                        validated_data = {}
                                        for field_name, field in self.fields.items():
                                            if field_name in data:
                                                validated_data[field_name] = field.to_internal_value(data[field_name])
                                        
                                        # Ejecutar validate() manualmente
                                        return self.validate(validated_data)
                        except Exception as inner_error:
                            # Si hay error interno, re-lanzar el error original
                            pass
            
            # Re-lanzar el error original si no se puede manejar
            raise

    def create(self, validated_data):
        """
        Create user with hashed password.
        """
        password = validated_data.pop('password')
        user = User.objects.create_user(
            password=password,
            **validated_data
        )
        return user


class UserCreateByAdminSerializer(serializers.ModelSerializer):
    """
    Serializer for creating users by admin.
    Includes role and status fields.
    """
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={'input_type': 'password'}
    )

    class Meta:
        model = User
        fields = [
            'full_name',
            'id_type',
            'id_number',
            'email_primary',
            'phone',
            'birth_date',
            'password',
            'email_secondary',
            'address',
            'profile_photo_url',
            'role',
            'status',
        ]
        extra_kwargs = {
            'full_name': {'required': True},
            'id_type': {'required': True},
            'id_number': {'required': True},
            'email_primary': {'required': True},
            'phone': {'required': True},
            'birth_date': {'required': True},
            'role': {'required': True},
            'status': {'required': True},
            'email_secondary': {'required': False, 'allow_blank': True},
            'address': {'required': False, 'allow_blank': True},
            'profile_photo_url': {'required': False, 'allow_blank': True},
        }

    def validate_email_primary(self, value):
        """
        Validate that email is unique.
        """
        value = value.strip().lower()
        if User.objects.filter(email_primary=value).exists():
            raise serializers.ValidationError('Este email ya está en uso')
        return value

    def validate_role(self, value):
        """
        Validate that role is valid.
        """
        valid_roles = [choice[0] for choice in User.Role.choices]
        if value not in valid_roles:
            raise serializers.ValidationError(f'Rol inválido. Opciones: {", ".join(valid_roles)}')
        return value

    def validate_status(self, value):
        """
        Validate that status is valid.
        """
        valid_statuses = [choice[0] for choice in User.Status.choices]
        if value not in valid_statuses:
            raise serializers.ValidationError(f'Estado inválido. Opciones: {", ".join(valid_statuses)}')
        return value

    def create(self, validated_data):
        """
        Create user with hashed password.
        """
        password = validated_data.pop('password')
        user = User.objects.create_user(
            password=password,
            **validated_data
        )
        return user


class UserUpdateByAdminSerializer(serializers.ModelSerializer):
    """
    Serializer for updating users by admin.
    Allows updating all fields except id and created_at.
    """
    password = serializers.CharField(
        write_only=True,
        required=False,
        validators=[validate_password],
        style={'input_type': 'password'}
    )

    class Meta:
        model = User
        fields = [
            'full_name',
            'id_type',
            'id_number',
            'email_primary',
            'phone',
            'birth_date',
            'password',
            'email_secondary',
            'address',
            'profile_photo_url',
            'role',
            'status',
        ]
        extra_kwargs = {
            'email_primary': {'required': False},
            'full_name': {'required': False},
            'id_type': {'required': False},
            'id_number': {'required': False},
            'phone': {'required': False},
            'birth_date': {'required': False},
            'role': {'required': False},
            'status': {'required': False},
            'email_secondary': {'required': False, 'allow_blank': True},
            'address': {'required': False, 'allow_blank': True},
            'profile_photo_url': {'required': False, 'allow_blank': True},
        }

    def validate_email_primary(self, value):
        """
        Validate that email is unique if it's being changed.
        """
        if value:
            value = value.strip().lower()
            # Excluir el usuario actual de la validación
            instance = self.instance
            if instance and User.objects.filter(email_primary=value).exclude(id=instance.id).exists():
                raise serializers.ValidationError('Este email ya está en uso')
        return value

    def validate_role(self, value):
        """
        Validate that role is valid.
        """
        if value:
            valid_roles = [choice[0] for choice in User.Role.choices]
            if value not in valid_roles:
                raise serializers.ValidationError(f'Rol inválido. Opciones: {", ".join(valid_roles)}')
        return value

    def validate_status(self, value):
        """
        Validate that status is valid.
        """
        if value:
            valid_statuses = [choice[0] for choice in User.Status.choices]
            if value not in valid_statuses:
                raise serializers.ValidationError(f'Estado inválido. Opciones: {", ".join(valid_statuses)}')
        return value

    def update(self, instance, validated_data):
        """
        Update user, handling password separately.
        """
        password = validated_data.pop('password', None)
        
        # Actualizar campos
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Actualizar password si se proporcionó
        if password:
            instance.set_password(password)
        
        instance.save()
        return instance


class UserMeUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for users to update their own profile.
    Only allows updating specific fields.
    """
    password = serializers.CharField(
        write_only=True,
        required=False,
        validators=[validate_password],
        style={'input_type': 'password'}
    )

    class Meta:
        model = User
        fields = [
            'full_name',
            'phone',
            'address',
            'email_secondary',
            'profile_photo_url',
            'password',
        ]
        extra_kwargs = {
            'full_name': {'required': False},
            'phone': {'required': False},
            'address': {'required': False, 'allow_blank': True},
            'email_secondary': {'required': False, 'allow_blank': True},
            'profile_photo_url': {'required': False, 'allow_blank': True},
        }

    # Campos prohibidos
    PROHIBITED_FIELDS = {
        'role',
        'status',
        'email_primary',
        'id_type',
        'id_number',
        'birth_date',
        'created_at',
        'updated_at',
        'last_login_at',
    }

    def validate(self, attrs):
        """
        Validate that prohibited fields are not being updated.
        """
        # Verificar que no se intenten actualizar campos prohibidos
        prohibited = set(attrs.keys()) & self.PROHIBITED_FIELDS
        if prohibited:
            raise serializers.ValidationError(
                f'No se pueden actualizar los siguientes campos: {", ".join(prohibited)}'
            )
        return attrs

    def update(self, instance, validated_data):
        """
        Update user profile, handling password separately.
        """
        password = validated_data.pop('password', None)
        
        # Actualizar campos permitidos
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Actualizar password si se proporcionó
        if password:
            instance.set_password(password)
        
        instance.save()
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for changing password (authenticated user).
    Requires current password and new password.
    """
    current_password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        help_text="Contraseña actual del usuario"
    )
    new_password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={'input_type': 'password'},
        help_text="Nueva contraseña que debe cumplir las políticas de seguridad"
    )

    def validate(self, attrs):
        """
        Validate that current password is correct and new password is different.
        """
        user = self.context['request'].user
        current_password = attrs.get('current_password')
        new_password = attrs.get('new_password')
        
        # Verificar contraseña actual
        if not user.check_password(current_password):
            raise serializers.ValidationError({
                'current_password': 'La contraseña actual es incorrecta'
            })
        
        # Verificar que la nueva contraseña sea diferente a la actual
        if user.check_password(new_password):
            raise serializers.ValidationError({
                'new_password': 'La nueva contraseña debe ser diferente a la actual'
            })
        
        return attrs


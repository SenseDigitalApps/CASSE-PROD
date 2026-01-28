"""
User service functions for user management operations.
"""
import logging
from typing import Dict, Any, Optional
from uuid import UUID

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError

from apps.audit.services.audit_log import log_audit_event
from apps.audit.constants import (
    USER_REGISTERED,
    USER_CREATED_BY_ADMIN,
    USER_UPDATED_BY_ADMIN,
    USER_UPDATED_SELF,
    USER_SUSPENDED,
    USER_ACTIVATED,
    USER_DELETED_SELF,
    PASSWORD_CHANGED,
)

User = get_user_model()
logger = logging.getLogger(__name__)

# Campos permitidos para actualización propia
SELF_EDITABLE_FIELDS = {
    'full_name',
    'phone',
    'address',
    'email_secondary',
    'profile_photo_url',
    'password',
}

# Campos prohibidos para actualización propia
SELF_PROHIBITED_FIELDS = {
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


def register_user(data: Dict[str, Any], ip_address: Optional[str] = None) -> User:
    """
    Registra un nuevo usuario (self-registration).
    
    Args:
        data: Diccionario con los datos del usuario
            - email_primary (requerido)
            - password (requerido)
            - full_name (requerido)
            - id_type (requerido)
            - id_number (requerido)
            - phone (requerido)
            - birth_date (requerido)
            - email_secondary (opcional)
            - address (opcional)
            - profile_photo_url (opcional)
        ip_address: IP del cliente (opcional)
    
    Returns:
        User: Usuario creado
    
    Raises:
        IntegrityError: Si el email ya existe
        ValidationError: Si faltan campos requeridos
    """
    try:
        # Extraer password antes de crear el usuario
        password = data.pop('password', None)
        if not password:
            raise ValidationError('El password es obligatorio')
        
        # Establecer valores por defecto
        data.setdefault('role', User.Role.CLIENT)
        data.setdefault('status', User.Status.ACTIVE)
        
        # Crear usuario
        user = User.objects.create_user(
            email_primary=data.pop('email_primary'),
            password=password,
            **data
        )
        
        # Generar audit log
        log_audit_event(
            actor_user=user,
            action=USER_REGISTERED,
            entity='User',
            entity_id=user.id,
            metadata={'email': user.email_primary, 'role': user.role},
            ip_address=ip_address
        )
        
        logger.info(f"Usuario registrado: {user.email_primary}")
        return user
        
    except IntegrityError as e:
        logger.error(f"Error de integridad al registrar usuario: {e}")
        raise ValidationError('El email ya está en uso')
    except Exception as e:
        logger.error(f"Error al registrar usuario: {e}", exc_info=True)
        raise


def create_user_by_admin(
    data: Dict[str, Any],
    actor_user: User,
    ip_address: Optional[str] = None
) -> User:
    """
    Crea un usuario por un administrador.
    
    Args:
        data: Diccionario con los datos del usuario (incluye role y status)
        actor_user: Usuario administrador que realiza la acción
        ip_address: IP del cliente (opcional)
    
    Returns:
        User: Usuario creado
    
    Raises:
        PermissionDenied: Si el actor_user no es ADMIN
        IntegrityError: Si el email ya existe
        ValidationError: Si faltan campos requeridos
    """
    # Validar permisos
    if actor_user.role != User.Role.ADMIN:
        raise PermissionDenied('Solo los administradores pueden crear usuarios')
    
    try:
        # Extraer password antes de crear el usuario
        password = data.pop('password', None)
        if not password:
            raise ValidationError('El password es obligatorio')
        
        # Crear usuario
        user = User.objects.create_user(
            email_primary=data.pop('email_primary'),
            password=password,
            **data
        )
        
        # Generar audit log
        log_audit_event(
            actor_user=actor_user,
            action=USER_CREATED_BY_ADMIN,
            entity='User',
            entity_id=user.id,
            metadata={
                'created_user_email': user.email_primary,
                'created_user_role': user.role,
                'created_user_status': user.status,
                'created_by': str(actor_user.id),
            },
            ip_address=ip_address
        )
        
        logger.info(f"Usuario creado por admin {actor_user.email_primary}: {user.email_primary}")
        return user
        
    except IntegrityError as e:
        logger.error(f"Error de integridad al crear usuario: {e}")
        raise ValidationError('El email ya está en uso')
    except Exception as e:
        logger.error(f"Error al crear usuario: {e}", exc_info=True)
        raise


def update_user_by_admin(
    user_id: UUID,
    data: Dict[str, Any],
    actor_user: User,
    ip_address: Optional[str] = None
) -> User:
    """
    Actualiza un usuario por un administrador.
    
    Args:
        user_id: ID del usuario a actualizar
        data: Diccionario con los campos a actualizar
        actor_user: Usuario administrador que realiza la acción
        ip_address: IP del cliente (opcional)
    
    Returns:
        User: Usuario actualizado
    
    Raises:
        PermissionDenied: Si el actor_user no es ADMIN
        User.DoesNotExist: Si el usuario no existe
    """
    # Validar permisos
    if actor_user.role != User.Role.ADMIN:
        raise PermissionDenied('Solo los administradores pueden actualizar usuarios')
    
    try:
        # Obtener usuario
        user = User.objects.get(id=user_id)
        
        # Guardar valores anteriores para el audit log
        old_values = {
            'role': user.role,
            'status': user.status,
            'email_primary': user.email_primary,
        }
        
        # Extraer password si está presente
        password = data.pop('password', None)
        
        # Actualizar campos
        for key, value in data.items():
            if hasattr(user, key):
                setattr(user, key, value)
        
        # Actualizar password si se proporcionó
        if password:
            user.set_password(password)
        
        # Guardar usuario
        user.save()
        
        # Preparar metadata para audit log
        metadata = {
            'updated_user_id': str(user.id),
            'updated_user_email': user.email_primary,
            'updated_by': str(actor_user.id),
        }
        
        # Agregar cambios relevantes
        changes = {}
        if old_values['role'] != user.role:
            changes['role'] = {'old': old_values['role'], 'new': user.role}
        if old_values['status'] != user.status:
            changes['status'] = {'old': old_values['status'], 'new': user.status}
        if old_values['email_primary'] != user.email_primary:
            changes['email_primary'] = {'old': old_values['email_primary'], 'new': user.email_primary}
        
        if changes:
            metadata['changes'] = changes
        
        # Generar audit log
        log_audit_event(
            actor_user=actor_user,
            action=USER_UPDATED_BY_ADMIN,
            entity='User',
            entity_id=user.id,
            metadata=metadata,
            ip_address=ip_address
        )
        
        logger.info(f"Usuario {user.email_primary} actualizado por admin {actor_user.email_primary}")
        return user
        
    except User.DoesNotExist:
        logger.error(f"Usuario con ID {user_id} no encontrado")
        raise
    except Exception as e:
        logger.error(f"Error al actualizar usuario: {e}", exc_info=True)
        raise


def update_self_user(
    user: User,
    data: Dict[str, Any],
    ip_address: Optional[str] = None
) -> User:
    """
    Actualiza el perfil propio del usuario.
    
    Args:
        user: Usuario que se actualiza a sí mismo
        data: Diccionario con los campos a actualizar (solo campos permitidos)
        ip_address: IP del cliente (opcional)
    
    Returns:
        User: Usuario actualizado
    
    Raises:
        ValidationError: Si se intenta actualizar campos prohibidos
    """
    # Validar que no se intenten actualizar campos prohibidos
    prohibited_fields = set(data.keys()) & SELF_PROHIBITED_FIELDS
    if prohibited_fields:
        raise ValidationError(
            f'No se pueden actualizar los siguientes campos: {", ".join(prohibited_fields)}'
        )
    
    # Filtrar solo campos permitidos
    allowed_data = {k: v for k, v in data.items() if k in SELF_EDITABLE_FIELDS}
    
    if not allowed_data:
        raise ValidationError('No hay campos válidos para actualizar')
    
    try:
        # Guardar valores anteriores para el audit log
        old_values = {key: getattr(user, key) for key in allowed_data.keys() if hasattr(user, key)}
        
        # Extraer password si está presente
        password = allowed_data.pop('password', None)
        
        # Actualizar campos permitidos
        for key, value in allowed_data.items():
            if hasattr(user, key):
                setattr(user, key, value)
        
        # Actualizar password si se proporcionó
        if password:
            user.set_password(password)
        
        # Guardar usuario
        user.save()
        
        # Preparar metadata para audit log
        metadata = {
            'updated_fields': list(allowed_data.keys()),
        }
        if password:
            metadata['password_changed'] = True
        
        # Generar audit log
        log_audit_event(
            actor_user=user,
            action=USER_UPDATED_SELF,
            entity='User',
            entity_id=user.id,
            metadata=metadata,
            ip_address=ip_address
        )
        
        logger.info(f"Usuario {user.email_primary} actualizó su perfil")
        return user
        
    except Exception as e:
        logger.error(f"Error al actualizar perfil propio: {e}", exc_info=True)
        raise


def suspend_user(
    user_id: UUID,
    actor_user: User,
    ip_address: Optional[str] = None
) -> User:
    """
    Suspende un usuario (solo administradores).
    
    Args:
        user_id: ID del usuario a suspender
        actor_user: Usuario administrador que realiza la acción
        ip_address: IP del cliente (opcional)
    
    Returns:
        User: Usuario suspendido
    
    Raises:
        PermissionDenied: Si el actor_user no es ADMIN
        User.DoesNotExist: Si el usuario no existe
    """
    # Validar permisos
    if actor_user.role != User.Role.ADMIN:
        raise PermissionDenied('Solo los administradores pueden suspender usuarios')
    
    try:
        # Obtener usuario
        user = User.objects.get(id=user_id)
        
        # Verificar que no esté ya suspendido
        if user.status == User.Status.SUSPENDED:
            logger.warning(f"Usuario {user.email_primary} ya está suspendido")
            return user
        
        # Suspender usuario
        user.status = User.Status.SUSPENDED
        user.save()
        
        # Generar audit log
        log_audit_event(
            actor_user=actor_user,
            action=USER_SUSPENDED,
            entity='User',
            entity_id=user.id,
            metadata={
                'suspended_user_email': user.email_primary,
                'suspended_by': str(actor_user.id),
            },
            ip_address=ip_address
        )
        
        logger.info(f"Usuario {user.email_primary} suspendido por admin {actor_user.email_primary}")
        return user
        
    except User.DoesNotExist:
        logger.error(f"Usuario con ID {user_id} no encontrado")
        raise
    except Exception as e:
        logger.error(f"Error al suspender usuario: {e}", exc_info=True)
        raise


def activate_user(
    user_id: UUID,
    actor_user: User,
    ip_address: Optional[str] = None
) -> User:
    """
    Activa un usuario (solo administradores).
    
    Args:
        user_id: ID del usuario a activar
        actor_user: Usuario administrador que realiza la acción
        ip_address: IP del cliente (opcional)
    
    Returns:
        User: Usuario activado
    
    Raises:
        PermissionDenied: Si el actor_user no es ADMIN
        User.DoesNotExist: Si el usuario no existe
    """
    # Validar permisos
    if actor_user.role != User.Role.ADMIN:
        raise PermissionDenied('Solo los administradores pueden activar usuarios')
    
    try:
        # Obtener usuario
        user = User.objects.get(id=user_id)
        
        # Verificar que no esté ya activo
        if user.status == User.Status.ACTIVE:
            logger.warning(f"Usuario {user.email_primary} ya está activo")
            return user
        
        # Activar usuario
        user.status = User.Status.ACTIVE
        user.save()
        
        # Generar audit log
        log_audit_event(
            actor_user=actor_user,
            action=USER_ACTIVATED,
            entity='User',
            entity_id=user.id,
            metadata={
                'activated_user_email': user.email_primary,
                'activated_by': str(actor_user.id),
            },
            ip_address=ip_address
        )
        
        logger.info(f"Usuario {user.email_primary} activado por admin {actor_user.email_primary}")
        return user
        
    except User.DoesNotExist:
        logger.error(f"Usuario con ID {user_id} no encontrado")
        raise
    except Exception as e:
        logger.error(f"Error al activar usuario: {e}", exc_info=True)
        raise


def delete_self_account(
    user: User,
    ip_address: Optional[str] = None
) -> User:
    """
    Elimina la cuenta del usuario (soft delete).
    Cambia el estado a DELETED y guarda la fecha de eliminación.
    
    Args:
        user: Usuario que elimina su propia cuenta
        ip_address: IP del cliente (opcional)
    
    Returns:
        User: Usuario con estado DELETED
    
    Raises:
        ValidationError: Si el usuario ya está eliminado
    """
    # Verificar que no esté ya eliminado
    if user.status == User.Status.DELETED:
        raise ValidationError('La cuenta ya ha sido eliminada')
    
    try:
        # Cambiar estado a DELETED
        user.status = User.Status.DELETED
        
        # Guardar fecha de eliminación
        from django.utils import timezone
        user.deleted_at = timezone.now()
        
        # Guardar usuario
        user.save(update_fields=['status', 'deleted_at'])
        
        # Generar audit log
        log_audit_event(
            actor_user=user,
            action=USER_DELETED_SELF,
            entity='User',
            entity_id=user.id,
            metadata={
                'email': user.email_primary,
                'deleted_at': user.deleted_at.isoformat(),
            },
            ip_address=ip_address
        )
        
        logger.info(f"Usuario {user.email_primary} eliminó su propia cuenta")
        return user
        
    except Exception as e:
        logger.error(f"Error al eliminar cuenta propia: {e}", exc_info=True)
        raise


def change_password(
    user: User,
    current_password: str,
    new_password: str,
    ip_address: Optional[str] = None
) -> User:
    """
    Cambia la contraseña del usuario autenticado.
    
    Args:
        user: Usuario que cambia su contraseña
        current_password: Contraseña actual del usuario
        new_password: Nueva contraseña
        ip_address: IP del cliente (opcional)
    
    Returns:
        User: Usuario actualizado
    
    Raises:
        ValidationError: Si la contraseña actual es incorrecta o la nueva contraseña no cumple validaciones
    """
    # Validar contraseña actual
    if not user.check_password(current_password):
        raise ValidationError('La contraseña actual es incorrecta')
    
    # Validar que la nueva contraseña sea diferente
    if user.check_password(new_password):
        raise ValidationError('La nueva contraseña debe ser diferente a la actual')
    
    try:
        # Cambiar contraseña
        user.set_password(new_password)
        user.save(update_fields=['password'])
        
        # Generar audit log
        log_audit_event(
            actor_user=user,
            action=PASSWORD_CHANGED,
            entity='User',
            entity_id=user.id,
            metadata={
                'email': user.email_primary,
                'password_changed': True,
            },
            ip_address=ip_address
        )
        
        logger.info(f"Usuario {user.email_primary} cambió su contraseña")
        return user
        
    except Exception as e:
        logger.error(f"Error al cambiar contraseña: {e}", exc_info=True)
        raise


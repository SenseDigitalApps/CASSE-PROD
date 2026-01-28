"""
User model for the insurance application.
"""
import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone


class UserManager(BaseUserManager):
    """Manager for custom User model."""

    def create_user(self, email_primary, password=None, **extra_fields):
        """Create and save a regular user."""
        if not email_primary:
            raise ValueError('El email_primary es obligatorio')
        
        email_primary = self.normalize_email(email_primary)
        user = self.model(email_primary=email_primary, **extra_fields)
        
        if password:
            user.set_password(password)
        
        user.save(using=self._db)
        return user

    def create_superuser(self, email_primary, password=None, **extra_fields):
        """Create and save a superuser."""
        # Establecer role como ADMIN (is_staff e is_superuser son propiedades calculadas)
        extra_fields.setdefault('role', User.Role.ADMIN)
        extra_fields.setdefault('status', User.Status.ACTIVE)
        # NO establecer is_staff e is_superuser - son propiedades calculadas desde role
        # extra_fields.setdefault('is_staff', True)  # Removido - es una propiedad
        # extra_fields.setdefault('is_superuser', True)  # Removido - es una propiedad

        if extra_fields.get('role') != User.Role.ADMIN:
            raise ValueError('Superuser debe tener role=ADMIN')
        if extra_fields.get('status') != User.Status.ACTIVE:
            raise ValueError('Superuser debe tener status=ACTIVE')

        return self.create_user(email_primary, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom User model for the insurance application."""

    class IdType(models.TextChoices):
        CC = 'CC', 'Cédula de Ciudadanía'
        CE = 'CE', 'Cédula de Extranjería'
        NIT = 'NIT', 'NIT'
        PASSPORT = 'PASSPORT', 'Pasaporte'
        TI = 'TI', 'Tarjeta de Identidad'

    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Administrador'
        CLIENT = 'CLIENT', 'Cliente'
        INTERVENTORIA = 'INTERVENTORIA', 'Interventoría'
        SUPERVISOR = 'SUPERVISOR', 'Supervisor'

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Activo'
        SUSPENDED = 'SUSPENDED', 'Suspendido'
        DELETED = 'DELETED', 'Eliminado'

    # Primary key
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Personal information
    full_name = models.CharField(max_length=255, verbose_name='Nombres y Apellidos')
    id_type = models.CharField(
        max_length=20,
        choices=IdType.choices,
        verbose_name='Tipo de Identificación'
    )
    id_number = models.CharField(max_length=50, verbose_name='Número de Identificación')
    birth_date = models.DateField(verbose_name='Fecha de Nacimiento')
    phone = models.CharField(max_length=20, verbose_name='Teléfono')
    address = models.TextField(null=True, blank=True, verbose_name='Dirección')
    profile_photo_url = models.URLField(null=True, blank=True, verbose_name='URL Foto de Perfil')

    # Email
    email_primary = models.EmailField(unique=True, verbose_name='Email Principal')
    email_secondary = models.EmailField(null=True, blank=True, verbose_name='Email Secundario')

    # Role and status
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CLIENT,
        verbose_name='Rol'
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name='Estado'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de Creación')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Fecha de Actualización')
    last_login_at = models.DateTimeField(null=True, blank=True, verbose_name='Último Inicio de Sesión')
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name='Fecha de Eliminación')

    # Django auth fields
    USERNAME_FIELD = 'email_primary'
    REQUIRED_FIELDS = ['full_name', 'id_type', 'id_number', 'phone', 'birth_date']

    objects = UserManager()

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'
        unique_together = [('id_type', 'id_number')]
        indexes = [
            models.Index(fields=['email_primary']),
            models.Index(fields=['role', 'status']),
            models.Index(fields=['id_type', 'id_number']),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.email_primary})"

    @property
    def username(self):
        """Return email_primary as username for compatibility with Django admin and Unfold."""
        return self.email_primary

    @property
    def email(self):
        """Return email_primary as email for compatibility with Django admin and Unfold."""
        return self.email_primary

    def get_full_name(self):
        """Return the full name of the user."""
        return self.full_name

    def get_short_name(self):
        """Return the short name for the user (first name or full name)."""
        return self.full_name.split()[0] if self.full_name else self.email_primary

    @property
    def is_active(self):
        """Return True if user is active."""
        return self.status == self.Status.ACTIVE

    @property
    def is_staff(self):
        """Return True if user is staff (admin)."""
        return self.role == self.Role.ADMIN

    @property
    def is_superuser(self):
        """Return True if user is superuser (admin)."""
        return self.role == self.Role.ADMIN

    def save(self, *args, **kwargs):
        """Override save to update last_login_at if needed."""
        super().save(*args, **kwargs)


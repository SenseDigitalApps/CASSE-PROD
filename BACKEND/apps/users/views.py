"""
Views for user management endpoints.
"""
import logging
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotFound, PermissionDenied
from django.core.exceptions import ValidationError

from .models import User
from .serializers import (
    UserPublicSerializer,
    UserRegisterSerializer,
    UserCreateByAdminSerializer,
    UserUpdateByAdminSerializer,
    UserMeUpdateSerializer,
    ChangePasswordSerializer,
)
from .permissions import IsAdmin, IsAdminOrReadOnly, IsOwnerOrAdmin
from .selectors.users import get_user_by_id, list_users
from .services.users import (
    create_user_by_admin,
    update_user_by_admin,
    update_self_user,
    suspend_user,
    activate_user,
    delete_self_account,
    change_password,
)

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


class UserMeView(APIView):
    """
    View for user's own profile.
    GET /api/v1/users/me/ - Get own profile
    PATCH /api/v1/users/me/ - Update own profile
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Get current user's profile.
        """
        serializer = UserPublicSerializer(
            request.user,
            context={'request': request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        """
        Update current user's profile.
        """
        serializer = UserMeUpdateSerializer(
            instance=request.user,
            data=request.data,
            partial=True
        )
        
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        ip_address = get_client_ip(request)
        
        try:
            user = update_self_user(
                user=request.user,
                data=serializer.validated_data,
                ip_address=ip_address
            )
        except Exception as e:
            logger.error(f"Error al actualizar perfil propio: {e}", exc_info=True)
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        response_serializer = UserPublicSerializer(
            user,
            context={'request': request}
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class UserListView(ListCreateAPIView):
    """
    View for listing and creating users.
    GET /api/v1/users/ - List users (with filters and pagination)
    POST /api/v1/users/ - Create user (ADMIN only)
    """
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]
    serializer_class = UserPublicSerializer

    def get_queryset(self):
        """
        Get queryset of users with filters applied.
        """
        # Obtener filtros de query params
        filters = {
            'role': self.request.query_params.get('role'),
            'status': self.request.query_params.get('status'),
            'search': self.request.query_params.get('search'),
        }
        
        # Remover None values
        filters = {k: v for k, v in filters.items() if v is not None}
        
        # Usar selector (valida permisos internamente)
        queryset = list_users(
            filters=filters if filters else None,
            actor_user=self.request.user
        )
        
        return queryset

    def get_serializer_class(self):
        """
        Return appropriate serializer class based on request method.
        """
        if self.request.method == 'POST':
            return UserCreateByAdminSerializer
        return UserPublicSerializer

    def create(self, request, *args, **kwargs):
        """
        Create a new user (ADMIN only).
        """
        serializer = self.get_serializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        ip_address = get_client_ip(request)
        
        try:
            user = create_user_by_admin(
                data=serializer.validated_data,
                actor_user=request.user,
                ip_address=ip_address
            )
        except PermissionDenied:
            return Response(
                {'detail': 'No tiene permisos para crear usuarios'},
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            logger.error(f"Error al crear usuario: {e}", exc_info=True)
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        response_serializer = UserPublicSerializer(
            user,
            context={'request': request}
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class UserDetailView(RetrieveUpdateAPIView):
    """
    View for retrieving and updating a specific user.
    GET /api/v1/users/{id}/ - Get user details
    PATCH /api/v1/users/{id}/ - Update user (ADMIN only)
    """
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]
    serializer_class = UserPublicSerializer
    lookup_field = 'id'
    lookup_url_kwarg = 'id'

    def get_queryset(self):
        """
        Get queryset (not used directly, but required by RetrieveUpdateAPIView).
        """
        return User.objects.all()

    def get_object(self):
        """
        Get user by ID using selector.
        """
        user_id = self.kwargs.get('id')
        try:
            user = get_user_by_id(user_id)
        except User.DoesNotExist:
            raise NotFound('Usuario no encontrado')
        
        # Verificar permisos de objeto
        self.check_object_permissions(self.request, user)
        
        return user

    def get_serializer_class(self):
        """
        Return appropriate serializer class based on request method.
        """
        if self.request.method == 'PATCH':
            # Solo ADMIN puede actualizar
            if self.request.user.role != User.Role.ADMIN:
                raise PermissionDenied('Solo los administradores pueden actualizar usuarios')
            return UserUpdateByAdminSerializer
        return UserPublicSerializer

    def update(self, request, *args, **kwargs):
        """
        Update user (ADMIN only).
        """
        # Verificar que sea ADMIN
        if request.user.role != User.Role.ADMIN:
            return Response(
                {'detail': 'Solo los administradores pueden actualizar usuarios'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        instance = self.get_object()
        serializer = UserUpdateByAdminSerializer(
            instance=instance,
            data=request.data,
            partial=True
        )
        
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        ip_address = get_client_ip(request)
        
        try:
            user = update_user_by_admin(
                user_id=instance.id,
                data=serializer.validated_data,
                actor_user=request.user,
                ip_address=ip_address
            )
        except Exception as e:
            logger.error(f"Error al actualizar usuario: {e}", exc_info=True)
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        response_serializer = UserPublicSerializer(
            user,
            context={'request': request}
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class UserSuspendView(APIView):
    """
    View for suspending a user.
    POST /api/v1/users/{id}/suspend/ - Suspend user (ADMIN only)
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, id):
        """
        Suspend a user.
        """
        ip_address = get_client_ip(request)
        
        try:
            user = suspend_user(
                user_id=id,
                actor_user=request.user,
                ip_address=ip_address
            )
        except User.DoesNotExist:
            return Response(
                {'detail': 'Usuario no encontrado'},
                status=status.HTTP_404_NOT_FOUND
            )
        except PermissionDenied:
            return Response(
                {'detail': 'No tiene permisos para suspender usuarios'},
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            logger.error(f"Error al suspender usuario: {e}", exc_info=True)
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(
            {'detail': 'user suspended'},
            status=status.HTTP_200_OK
        )


class UserActivateView(APIView):
    """
    View for activating a user.
    POST /api/v1/users/{id}/activate/ - Activate user (ADMIN only)
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, id):
        """
        Activate a user.
        """
        ip_address = get_client_ip(request)
        
        try:
            user = activate_user(
                user_id=id,
                actor_user=request.user,
                ip_address=ip_address
            )
        except User.DoesNotExist:
            return Response(
                {'detail': 'Usuario no encontrado'},
                status=status.HTTP_404_NOT_FOUND
            )
        except PermissionDenied:
            return Response(
                {'detail': 'No tiene permisos para activar usuarios'},
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            logger.error(f"Error al activar usuario: {e}", exc_info=True)
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(
            {'detail': 'user activated'},
            status=status.HTTP_200_OK
        )


class DeleteSelfAccountView(APIView):
    """
    View for user to delete their own account.
    POST /api/v1/users/me/delete/ - Delete own account
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Delete current user's account (soft delete).
        Changes status to DELETED and prevents future logins.
        """
        ip_address = get_client_ip(request)
        
        try:
            delete_self_account(
                user=request.user,
                ip_address=ip_address
            )
        except ValidationError as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error al eliminar cuenta propia: {e}", exc_info=True)
            return Response(
                {'detail': 'Error al procesar solicitud de eliminación'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        return Response(
            {'status': 'usuario eliminado correctamente'},
            status=status.HTTP_200_OK
        )


class ChangePasswordView(APIView):
    """
    View for authenticated user to change their password.
    POST /api/v1/users/me/change-password/
    
    Requires current password and new password.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Change current user's password.
        """
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        ip_address = get_client_ip(request)
        current_password = serializer.validated_data['current_password']
        new_password = serializer.validated_data['new_password']
        
        try:
            change_password(
                user=request.user,
                current_password=current_password,
                new_password=new_password,
                ip_address=ip_address
            )
        except ValidationError as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error al cambiar contraseña: {e}", exc_info=True)
            return Response(
                {'detail': 'Error al procesar solicitud de cambio de contraseña'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        return Response(
            {'message': 'Contraseña cambiada correctamente'},
            status=status.HTTP_200_OK
        )


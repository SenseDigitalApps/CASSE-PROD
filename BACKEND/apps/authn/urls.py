"""
URLs for authentication endpoints.
"""
from django.urls import path
from .views import (
    LoginView, 
    RegisterView, 
    RefreshTokenView,
    VerifyOTPView,
    ResendOTPView,
    PasswordResetRequestView,
    PasswordResetVerifyOTPView
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify_otp'),
    path('resend-otp/', ResendOTPView.as_view(), name='resend_otp'),
    path('password-reset/request/', PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('password-reset/verify/', PasswordResetVerifyOTPView.as_view(), name='password-reset-verify'),
    path('jwt/refresh/', RefreshTokenView.as_view(), name='token_refresh'),
]


from django.urls import path

from .views import PaymentConfirmView, PaymentDetailView, TravelQuotePaymentInitiateView

urlpatterns = [
    path(
        'travel-quotes/<uuid:quote_id>/initiate/',
        TravelQuotePaymentInitiateView.as_view(),
        name='travel-quote-payment-initiate',
    ),
    path('<uuid:payment_id>/', PaymentDetailView.as_view(), name='payment-detail'),
    path('<uuid:payment_id>/confirm/', PaymentConfirmView.as_view(), name='payment-confirm'),
]

from django.urls import path

from .views import VoucherDetailView, VoucherIssueView, VoucherListView, VoucherPdfView

urlpatterns = [
    path('', VoucherListView.as_view(), name='voucher-list'),
    path('issue/', VoucherIssueView.as_view(), name='voucher-issue'),
    path('<uuid:voucher_id>/', VoucherDetailView.as_view(), name='voucher-detail'),
    path('<uuid:voucher_id>/pdf/', VoucherPdfView.as_view(), name='voucher-pdf'),
]

"""SOAP clients for Universal Assistance Siebel services."""

from .base import SiebelSoapClient
from .lead_cotizador import LeadCotizadorClient
from .voucher import VoucherClient
from .query_portal import QueryVoucherPortalClient
from .send_report import SendReportClient
from .lead_service import LeadServiceClient

__all__ = [
    'SiebelSoapClient',
    'LeadCotizadorClient',
    'VoucherClient',
    'QueryVoucherPortalClient',
    'SendReportClient',
    'LeadServiceClient',
]

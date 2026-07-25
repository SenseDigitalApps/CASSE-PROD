"""SOAP/API clients for insurer integrations (UA + Allianz)."""

from .allianz_autos import AllianzAutosClient
from .allianz_hogar import AllianzHogarClient
from .base import SiebelSoapClient
from .lead_cotizador import LeadCotizadorClient
from .voucher import VoucherClient
from .query_portal import QueryVoucherPortalClient
from .send_report import SendReportClient
from .lead_service import LeadServiceClient

__all__ = [
    'AllianzAutosClient',
    'AllianzHogarClient',
    'SiebelSoapClient',
    'LeadCotizadorClient',
    'VoucherClient',
    'QueryVoucherPortalClient',
    'SendReportClient',
    'LeadServiceClient',
]

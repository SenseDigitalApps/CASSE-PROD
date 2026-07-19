"""Client for UA Query Voucher Portal WS."""
from __future__ import annotations

from apps.integrations.constants import SERVICE_QUERY_PORTAL, WSDL_FILES
from apps.integrations.clients.base import SiebelSoapClient, _serialize_for_log


class QueryVoucherPortalClient(SiebelSoapClient):
    """Completes voucher issuance when CASSE handles documentation."""

    service_name = SERVICE_QUERY_PORTAL
    binding_name = '{http://siebel.com/CustomUI}QueryVoucherPortalPort'

    def __init__(self, **kwargs):
        super().__init__(wsdl_filename=WSDL_FILES[SERVICE_QUERY_PORTAL], **kwargs)

    def query(self, *, voucher_number: str, organization: str) -> dict:
        result = self.call(
            'QueryVoucherPortalOper',
            VoucherNumber=voucher_number,
            Organization=organization,
        )
        return _serialize_for_log(result)

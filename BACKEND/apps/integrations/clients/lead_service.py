"""Client for Lead Service (retire lead after purchase)."""
from __future__ import annotations

from apps.integrations.constants import SERVICE_RETIRE_LEAD, WSDL_FILES
from apps.integrations.clients.base import SiebelSoapClient, _serialize_for_log


class LeadServiceClient(SiebelSoapClient):
    """Wraps LeadServiceRetireLead operation."""

    service_name = SERVICE_RETIRE_LEAD
    binding_name = '{http://siebel.com/marketing/leads}Lead_spcService'

    def __init__(self, **kwargs):
        super().__init__(wsdl_filename=WSDL_FILES[SERVICE_RETIRE_LEAD], **kwargs)

    def retire_lead(
        self,
        *,
        lead_id: str,
        reason_code: str,
        comments: str = '',
    ) -> dict:
        result = self.call(
            'LeadServiceRetireLead',
            Comments=comments,
            ReasonCode=reason_code,
            LeadId=lead_id,
        )
        return _serialize_for_log(result)

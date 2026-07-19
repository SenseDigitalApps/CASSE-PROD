"""Client for UA Send Report WS (voucher PDF)."""
from __future__ import annotations

import ast
import base64
from typing import Any

from apps.integrations.constants import SERVICE_SEND_REPORT, WSDL_FILES
from apps.integrations.clients.base import SiebelSoapClient, _serialize_for_log


class SendReportClient(SiebelSoapClient):
    """Fetches voucher PDF from Siebel."""

    service_name = SERVICE_SEND_REPORT
    binding_name = '{http://siebel.com/CustomUI}SendReportPort'

    def __init__(self, **kwargs):
        super().__init__(wsdl_filename=WSDL_FILES[SERVICE_SEND_REPORT], **kwargs)

    def get_report(
        self,
        *,
        voucher_number: str,
        organization: str,
        language: str = 'es',
        tariff: str = '',
    ) -> dict:
        result = self.call(
            'SendReportOper',
            Language=language,
            VoucherNumber=voucher_number,
            Tarifa=tariff,
            Organization=organization,
        )
        parsed = _serialize_for_log(result)
        pdf_data = self._extract_pdf(parsed)
        return {
            'pdf_base64': pdf_data,
            'raw': parsed,
        }

    def _normalize_pdf_buffer(self, buffer: Any) -> bytes | None:
        if buffer is None:
            return None
        if isinstance(buffer, bytes):
            return buffer
        if isinstance(buffer, str):
            stripped = buffer.strip()
            if stripped.startswith("b'") or stripped.startswith('b"'):
                try:
                    value = ast.literal_eval(stripped)
                    if isinstance(value, bytes):
                        return value
                except (SyntaxError, ValueError):
                    pass
            if stripped.startswith('%PDF'):
                return stripped.encode('latin-1')
            try:
                return base64.b64decode(stripped)
            except Exception:
                return stripped.encode('latin-1')
        return None

    def _extract_pdf(self, data: dict) -> bytes | None:
        sm = data.get('SM') or {}
        voucher_list = sm.get('ListOfUaSendReportIo') or {}
        vouchers = voucher_list.get('UaVoucherBc') or []
        if isinstance(vouchers, dict):
            vouchers = [vouchers]
        for voucher in vouchers:
            impresion = voucher.get('ListOfUaImpresionSimplificadaBc') or {}
            items = impresion.get('UaImpresionSimplificadaBc') or []
            if isinstance(items, dict):
                items = [items]
            for item in items:
                pdf_bytes = self._normalize_pdf_buffer(
                    item.get('ReportOutputFileBuffer')
                )
                if pdf_bytes:
                    return pdf_bytes
        return None

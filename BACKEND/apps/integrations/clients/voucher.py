"""Client for UA Operaciones Voucher WS (issue, query, cancel vouchers)."""
from __future__ import annotations

from typing import Any

from django.conf import settings

from lxml import etree
from zeep.helpers import serialize_object

from apps.integrations.constants import SERVICE_VOUCHER, WSDL_FILES
from apps.integrations.clients.base import SiebelSoapClient, _serialize_for_log


class VoucherClient(SiebelSoapClient):
    """Wraps Alta, Consulta and Anula voucher operations."""

    service_name = SERVICE_VOUCHER
    binding_name = '{http://siebel.com/CustomUI}Alta_Voucher_Port'

    def __init__(self, **kwargs):
        super().__init__(wsdl_filename=WSDL_FILES[SERVICE_VOUCHER], **kwargs)

    def issue(self, *, voucher_data: dict[str, Any]) -> dict[str, Any]:
        payload = self._build_issue_request(voucher_data)
        result = self.call(
            'Alta_Voucher_Operation',
            UAAltaVoucheMinRequest=payload['UAAltaVoucheMinRequest'],
        )
        return self._parse_issue_response(result)

    def query(self, *, organization: str, control_number: str) -> dict[str, Any]:
        payload = {
            'UAConsultaVoucherRequest': {
                'ConsultaDatosVoucherReq': {
                    'OrganizacionRegistradoraConsulta': organization,
                    'NroControlConsulta': control_number,
                }
            }
        }
        result = self.call(
            'Consulta_Voucher_Operation',
            Consulta_Voucher_Operation_Input=payload,
        )
        return _serialize_for_log(result)

    def cancel(self, *, agency: str, voucher_number: str) -> dict[str, Any]:
        result = self.call(
            'Anula_Voucher_Operation',
            Anula_Voucher_Operation_Input={
                'AgenciaAnulacion': agency,
                'NroVoucherSiebelAnulacion': voucher_number,
            },
        )
        return _serialize_for_log(result)

    def _build_issue_request(self, data: dict[str, Any]) -> dict[str, Any]:
        applicants = data.get('applicants') or [{}]
        applicant_nodes = [self._build_applicant(a) for a in applicants]

        voucher = {
            'NroControl': data['control_number'],
            'Vendedor': data.get('vendor', settings.UA_VENDOR_CODE),
            'Canal': data.get('channel', settings.UA_CHANNEL),
            'TipoVenta': data.get('sale_type', 'Individual'),
            'Precio': str(data['price']),
            'PrecioEmision': str(data.get('price_emission', data['price'])),
            'FechaEmision': data['issue_date'],
            'FechaVigencia': data['start_date'],
            'FechaFinal': data['end_date'],
            'Destino': data['destination'],
            'MonedaLista': data.get('currency', 'USD'),
            'LeadId': data.get('lead_id', '') or '',
            'EnvioVoucherMail': data.get('send_email', 'N'),
            'PostProcesoFlag': data.get('post_process', 'Y'),
            'Contrato': data.get('contract_id', '') or '',
            'DatosSolicitante': applicant_nodes,
            'DatosProducto': [{
                'NombreProducto': data['product_name'],
                'NroPreCompra': data.get('pre_purchase', '') or '',
            }],
            'DatosAgencia': {
                'OrganizacionRegistradora': data.get(
                    'organization_id', settings.UA_ORGANIZATION_ID
                ),
            },
        }
        return {'UAAltaVoucheMinRequest': {'DatosVoucher': [voucher]}}

    def _build_applicant(self, applicant: dict[str, Any]) -> dict[str, Any]:
        node = {
            'NroPolizaSeguro': applicant.get('policy_number', '0'),
            'TipoDocumentoSolicitante': applicant['document_type'],
            'NroDocumentoSolicitante': applicant['document_number'],
            'NombreSolicitante': applicant['first_name'],
            'ApellidoSolicitante': applicant['last_name'],
            'FechaNacimientoSolicitante': applicant['birth_date'],
            'PaisResidenciaSolicitante': applicant.get(
                'residence_country', settings.UA_DEFAULT_ORIGIN_COUNTRY
            ),
            'CorreoElectronicoSolicitante': applicant.get('email', '') or '',
            'NroTelCelularSolicitante': applicant.get('phone', '') or '',
        }
        if applicant.get('city'):
            node['DatosDomicilioSolicitante'] = [{
                'Ciudad': applicant['city'],
                'Pais': (
                    applicant.get('country')
                    or applicant.get('residence_country')
                    or settings.UA_DEFAULT_ORIGIN_COUNTRY
                ),
            }]
        return node

    def _parse_issue_response(self, result: Any) -> dict[str, Any]:
        items = self._extract_output_items(result)
        first = items[0] if items else {}
        error_msg = first.get('ErrorMsg') or first.get('Error_spcMsg')
        return {
            'voucher_number': first.get('NroVoucher'),
            'control_number': first.get('NroControlExt'),
            'error_code': first.get('ErrorCode'),
            'error_message': error_msg,
            'raw': _serialize_for_log(result),
        }

    def _flatten_response_item(self, item: Any) -> dict[str, Any]:
        if isinstance(item, dict):
            data = dict(item)
        else:
            try:
                data = dict(serialize_object(item))
            except Exception:
                data = {}

        raw_elements = data.pop('_raw_elements', None)
        if raw_elements is None and hasattr(item, '_raw_elements'):
            raw_elements = item._raw_elements

        if raw_elements:
            for element in raw_elements:
                tag = etree.QName(element).localname
                text = (element.text or '').strip()
                if text and not data.get(tag):
                    data[tag] = text
        return data

    def _extract_output_items(self, result: Any) -> list[dict[str, Any]]:
        if isinstance(result, list):
            raw_items = result
        else:
            data = _serialize_for_log(result)
            if not isinstance(data, dict):
                return []
            resp = data.get('UAAltaVoucheMinResponse') or data
            raw_items = resp.get('DatosVoucherResp') or []
            if isinstance(raw_items, dict):
                raw_items = [raw_items]

        return [self._flatten_response_item(item) for item in raw_items]

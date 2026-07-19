"""Client for UA Lead Cotizador WS (quote / requote travel assistance)."""
from __future__ import annotations

from typing import Any

from django.conf import settings

from zeep.helpers import serialize_object

from apps.integrations.constants import SERVICE_LEAD_COTIZADOR, WSDL_FILES
from apps.integrations.clients.base import SiebelSoapClient, _serialize_for_log


class LeadCotizadorClient(SiebelSoapClient):
    """Wraps LeadCotizadorOper SOAP operation."""

    service_name = SERVICE_LEAD_COTIZADOR
    binding_name = '{http://siebel.com/CustomUI}LeadCotizadorPort'

    def __init__(self, **kwargs):
        super().__init__(wsdl_filename=WSDL_FILES[SERVICE_LEAD_COTIZADOR], **kwargs)

    def quote(self, *, datos: dict[str, Any]) -> dict[str, Any]:
        """
        Create or update a lead and return available products.

        datos keys map to DatosLeadCotizadorIn fields (PaisOrigen, Destino, etc.).
        """
        payload = self._build_request(datos)
        result = self.call(
            'LeadCotizadorOper',
            UALeadCotizadorReq=payload['UALeadCotizadorReq'],
        )
        return self._parse_response(result)

    def _build_request(self, datos: dict[str, Any]) -> dict[str, Any]:
        ages = datos.get('ages') or []
        age_fields = {f'Edad{i}': '' for i in range(1, 11)}
        for idx, age in enumerate(ages[:10], start=1):
            age_fields[f'Edad{idx}'] = str(age)

        affiliate_type = datos.get('affiliate_type', 'INDIVIDUAL')
        convenio = (
            settings.UA_CONVENIO_CAVIPETROL_ID
            if affiliate_type == 'CAVIPETROL'
            else settings.UA_CONVENIO_INDIVIDUAL_ID
        )

        lead_data = {
            'IdLead': datos.get('lead_id', '') or '',
            'OrganizacionEmisora': datos.get(
                'organization_id', settings.UA_ORGANIZATION_ID
            ),
            'CantCotizaciones': str(datos.get('quote_count', 0)),
            'Convenio': datos.get('convenio', convenio) or '',
            'Folleto': datos.get('folleto', '') or '',
            'PaisOrigen': datos.get('origin_country', settings.UA_DEFAULT_ORIGIN_COUNTRY),
            'Destino': datos['destination'],
            'TipoViaje': datos['trip_type'],
            'FechaInicio': datos['start_date'],
            'FechaFin': datos['end_date'],
            'CantidadPasajeros': str(datos['passenger_count']),
            'PackFamiliar': datos.get('family_pack', '') or '',
            **age_fields,
            'ApellidoContacto': datos.get('contact_last_name', '') or '',
            'NombreContacto': datos.get('contact_first_name', '') or '',
            'TelefonoContacto': datos.get('contact_phone', '') or '',
            'EmailContacto': datos.get('contact_email', '') or '',
            'Categoria': datos.get('category', '') or '',
            'Precompras': datos.get('precompras', '') or '',
            'NroDocumento': datos.get('document_number', '') or '',
            'TipoDocumento': datos.get('document_type', '') or '',
        }

        return {
            'UALeadCotizadorReq': {
                'DatosLeadCotizadorIn': lead_data,
            }
        }

    def _parse_response(self, result: Any) -> dict[str, Any]:
        items = self._extract_output_items(result)
        products = []

        for item in items:
            attrs = item.get('Atributo') or []
            if isinstance(attrs, dict):
                attrs = [attrs]
            products.append({
                'lead_id': item.get('IdLeadOut'),
                'product_id': item.get('IdProducto'),
                'product_name': item.get('NombreProducto') or item.get('Producto'),
                'family': item.get('FamiliaProducto'),
                'category': item.get('Categoria'),
                'brand': item.get('Marca'),
                'logo': item.get('Logo'),
                'prices': {
                    'emission': item.get('PrecioEmision'),
                    'emission_local': item.get('PrecioEmisionLocal'),
                    'gross': item.get('PrecioBruto'),
                    'gross_local': item.get('PrecioBrutoLocal'),
                    'unit': item.get('PrecioUnitario'),
                    'net': item.get('PrecioNeto'),
                    'net_local': item.get('PrecioNetoLocal'),
                    'currency': item.get('MonedaLista'),
                    'currency_local': item.get('MonedaLocal'),
                    'exchange_rate': item.get('TipoCambio'),
                },
                'coverage_attributes': [
                    {
                        'name': a.get('Nombre'),
                        'visible_name': a.get('NombreVisible'),
                        'unit': a.get('Unidad'),
                        'value': a.get('Valor'),
                    }
                    for a in attrs
                ],
                'geographic_scope': item.get('AmbitoGeografico'),
                'age_limit_lower': item.get('LimiteEdadInferior'),
                'age_limit_upper': item.get('LimiteEdadSuperior'),
                'error_code': item.get('ErrorCode'),
                'error_message': item.get('ErrorMsg'),
            })

        lead_id = products[0]['lead_id'] if products else None
        return {
            'lead_id': lead_id,
            'products': products,
            'raw': _serialize_for_log(result),
        }

    def _extract_output_items(self, result: Any) -> list[dict[str, Any]]:
        if isinstance(result, list):
            raw_items = result
        else:
            data = _serialize_for_log(result)
            if not isinstance(data, dict):
                return []
            resp = data.get('UALeadCotizadorResp') or data
            raw_items = resp.get('DatosLeadCotizadorOut') or []
            if isinstance(raw_items, dict):
                raw_items = [raw_items]

        items: list[dict[str, Any]] = []
        for item in raw_items:
            if isinstance(item, dict):
                items.append(item)
                continue
            try:
                items.append(serialize_object(item))
            except Exception:
                serialized = _serialize_for_log(item)
                if isinstance(serialized, dict):
                    items.append(serialized)
        return items

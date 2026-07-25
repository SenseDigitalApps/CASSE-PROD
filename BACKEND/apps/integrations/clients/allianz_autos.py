"""
Allianz Autos Individual (ramos 1241/1243) Call4 SOAP client.

Uses mTLS (PFX/PEM) against AutosIndividualWS.operation `call`, with the
Call4 <chargerequest> XML as the `xml` string parameter (CDATA).
"""
from __future__ import annotations

import html
import logging
import re
import tempfile
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from django.conf import settings
from lxml import etree
import requests

from apps.integrations.exceptions import IntegrationError, SiebelBusinessError, SiebelSoapError
from apps.integrations.models import IntegrationCallLog

logger = logging.getLogger(__name__)

ALLIANZ_NS = 'http://ws.allianz.com'
SOAP_NS = 'http://schemas.xmlsoap.org/soap/envelope/'


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value).replace(',', '').strip())
    except (InvalidOperation, ValueError):
        return None


def _text(node: etree._Element | None, default: str = '') -> str:
    if node is None or node.text is None:
        return default
    return str(node.text).strip()


def _child_text(parent: etree._Element, tag: str, default: str = '') -> str:
    child = parent.find(tag)
    if child is None:
        # Case-insensitive fallback for mixed Allianz casing.
        for el in parent:
            if el.tag and el.tag.lower() == tag.lower():
                return _text(el, default)
        return default
    return _text(child, default)


class AllianzAutosClient:
    """mTLS SOAP client for Allianz Autos Individual Call4 tarificación."""

    service_name = 'allianz_autos'

    def __init__(self, *, actor_user=None, correlation_id: str = ''):
        self.actor_user = actor_user
        self.correlation_id = correlation_id
        self._cert_files: tuple[str, str] | None = None
        self._temp_dir: tempfile.TemporaryDirectory | None = None

    def close(self) -> None:
        if self._temp_dir is not None:
            self._temp_dir.cleanup()
            self._temp_dir = None
            self._cert_files = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def quote(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run Call4 tarificación (operationtypecode=TA) and parse packages."""
        if getattr(settings, 'ALLIANZ_MOCK', False):
            return self._mock_quote(payload)

        charge_xml = self.build_chargerequest(payload)
        return self.call(charge_xml=charge_xml)

    def call(self, *, charge_xml: str) -> dict[str, Any]:
        started = time.monotonic()
        status = IntegrationCallLog.Status.SUCCESS
        error_message = ''
        response_text = ''
        parsed: dict[str, Any] | None = None
        envelope = self._build_soap_envelope(charge_xml)

        try:
            response_text = self._post_soap(envelope)
            parsed = self._parse_call_response(response_text)
            return parsed
        except SiebelBusinessError as exc:
            status = IntegrationCallLog.Status.ERROR
            error_message = str(exc)
            raise
        except requests.Timeout as exc:
            status = IntegrationCallLog.Status.TIMEOUT
            error_message = f'Timeout Allianz Autos: {exc}'
            raise SiebelSoapError(error_message) from exc
        except Exception as exc:
            status = IntegrationCallLog.Status.ERROR
            error_message = str(exc)
            logger.exception('Allianz Autos call failed')
            if isinstance(exc, SiebelSoapError):
                raise
            raise SiebelSoapError(f'Error en llamada Allianz Autos: {exc}') from exc
        finally:
            duration_ms = int((time.monotonic() - started) * 1000)
            IntegrationCallLog.objects.create(
                service_name=self.service_name,
                operation='call',
                status=status,
                request_payload={
                    'soap_envelope': envelope,
                    'charge_xml': charge_xml,
                },
                response_payload={
                    'raw': response_text[:200000] if response_text else None,
                    'parsed': parsed,
                },
                error_message=error_message,
                duration_ms=duration_ms,
                correlation_id=self.correlation_id,
                actor_user=self.actor_user,
            )

    def build_chargerequest(self, payload: dict[str, Any]) -> str:
        auth = {
            'company': settings.ALLIANZ_COMPANY,
            'partnerid': settings.ALLIANZ_PARTNER_ID,
            'agentid': settings.ALLIANZ_AGENT_ID,
            'partnercode': settings.ALLIANZ_PARTNER_CODE or settings.ALLIANZ_PARTNER_ID,
            'agentcode': settings.ALLIANZ_AGENT_CODE,
        }
        for key, value in auth.items():
            if not value:
                raise IntegrationError(
                    f'Integración Allianz no configurada. Falta {key.upper()}.'
                )

        def tag(name: str, value: Any) -> str:
            if value is None or value == '':
                return ''
            return f'<{name}>{xml_escape(str(value))}</{name}>'

        risk_fields = [
            ('ownerborndate', payload.get('owner_born_date')),
            ('ownersex', payload.get('owner_sex')),
            ('repowered', payload.get('repowered', 'N')),
            ('protectiondevicecode', payload.get('protection_device_code', '4')),
            ('accessoriesvalue', payload.get('accessories_value', '0')),
            ('shieldingvalue', payload.get('shielding_value', '0')),
            ('gassystemvalue', payload.get('gas_system_value', '0')),
            ('isnewvehicle', payload.get('is_new_vehicle', 'N')),
            ('insuredvalue', payload.get('insured_value', '0')),
            ('continuity', payload.get('continuity', 'N')),
            ('circulationareadanecode', payload.get('circulation_dane_code')),
        ]
        risk_xml = ''.join(tag(k, v) for k, v in risk_fields if v is not None and v != '')

        body = [
            tag('transactionnumber', payload.get('transaction_number') or 'CASSE'),
            '<authentication>'
            + ''.join(tag(k, v) for k, v in auth.items())
            + '</authentication>',
            '<operationheaders>'
            + tag('operationtypecode', payload.get('operation_type_code', 'TA'))
            + tag('productcode', payload.get('product_code', settings.ALLIANZ_PRODUCT_CODE))
            + '</operationheaders>',
            tag('cap', payload.get('cap', settings.ALLIANZ_CAP)),
            tag('effectivedate', payload.get('effective_date')),
            tag('TermDate', payload.get('term_date')),
            tag('firstbill', payload.get('first_bill', '0')),
            tag('successive', payload.get('successive', '0')),
            tag('holderdoctype', payload.get('holder_doc_type', 'C')),
            tag('holderdocnumber', payload.get('holder_doc_number')),
            tag('ownerdoctype', payload.get('owner_doc_type') or payload.get('holder_doc_type', 'C')),
            tag('ownerdocnumber', payload.get('owner_doc_number') or payload.get('holder_doc_number')),
            tag('isholderdriver', payload.get('is_holder_driver', 'S')),
            tag('isholderowner', payload.get('is_holder_owner', 'S')),
            tag('isnewowner', payload.get('is_new_owner', 'S')),
            tag('risktype', payload.get('risk_type', settings.ALLIANZ_DEFAULT_RISK_TYPE)),
            tag('vehicleplate', payload.get('vehicle_plate')),
            tag('vehicleorigin', payload.get('vehicle_origin', settings.ALLIANZ_VEHICLE_ORIGIN)),
            tag('vehiclefasecoldacode', payload.get('fasecolda_code')),
            tag('vehicleyear', payload.get('vehicle_year')),
            f'<riskdata>{risk_xml}</riskdata>',
        ]
        return (
            '<chargerequest xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            + ''.join(part for part in body if part)
            + '</chargerequest>'
        )

    def _build_soap_envelope(self, charge_xml: str) -> str:
        # Prefer CDATA so nested XML is not double-escaped by intermediaries.
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<soapenv:Envelope xmlns:soapenv="{SOAP_NS}" xmlns:ws="{ALLIANZ_NS}">'
            '<soapenv:Header/>'
            '<soapenv:Body>'
            '<ws:call>'
            f'<ws:xml><![CDATA[{charge_xml}]]></ws:xml>'
            '</ws:call>'
            '</soapenv:Body>'
            '</soapenv:Envelope>'
        )

    def _cert_tuple(self) -> tuple[str, str]:
        if self._cert_files:
            return self._cert_files

        cert_pem = getattr(settings, 'ALLIANZ_CERT_PEM_PATH', '') or ''
        key_pem = getattr(settings, 'ALLIANZ_KEY_PEM_PATH', '') or ''
        if cert_pem and key_pem and Path(cert_pem).is_file() and Path(key_pem).is_file():
            self._cert_files = (cert_pem, key_pem)
            return self._cert_files

        pfx_path = getattr(settings, 'ALLIANZ_PFX_PATH', '') or ''
        pfx_password = getattr(settings, 'ALLIANZ_PFX_PASSWORD', '') or ''
        if not pfx_path or not Path(pfx_path).is_file():
            raise IntegrationError(
                'Integración Allianz no configurada. Falta certificado '
                '(ALLIANZ_PFX_PATH o ALLIANZ_CERT_PEM_PATH/ALLIANZ_KEY_PEM_PATH).'
            )

        try:
            from cryptography.hazmat.primitives.serialization import (
                Encoding,
                NoEncryption,
                PrivateFormat,
                pkcs12,
            )
        except ImportError as exc:
            raise IntegrationError(
                'Falta el paquete cryptography para leer el PFX de Allianz.'
            ) from exc

        raw = Path(pfx_path).read_bytes()
        key, cert, _extra = pkcs12.load_key_and_certificates(
            raw,
            pfx_password.encode('utf-8') if pfx_password else None,
        )
        if key is None or cert is None:
            raise IntegrationError('No se pudo leer clave/certificado del PFX Allianz.')

        self._temp_dir = tempfile.TemporaryDirectory(prefix='allianz_mtls_')
        cert_file = Path(self._temp_dir.name) / 'cert.pem'
        key_file = Path(self._temp_dir.name) / 'key.pem'
        cert_file.write_bytes(cert.public_bytes(Encoding.PEM))
        key_file.write_bytes(
            key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        )
        self._cert_files = (str(cert_file), str(key_file))
        return self._cert_files

    def _post_soap(self, envelope: str) -> str:
        endpoint = settings.ALLIANZ_ENDPOINT_URL
        timeout = int(getattr(settings, 'ALLIANZ_SOAP_TIMEOUT', 45))
        response = requests.post(
            endpoint,
            data=envelope.encode('utf-8'),
            headers={
                'Content-Type': 'text/xml; charset=utf-8',
                'SOAPAction': 'urn:call',
            },
            cert=self._cert_tuple(),
            timeout=(min(15, timeout), timeout),
        )
        body = response.text or ''
        if response.status_code >= 400:
            raise SiebelSoapError(
                f'Allianz HTTP {response.status_code}: {body[:500]}',
                details={'status_code': response.status_code, 'body': body[:2000]},
            )
        if 'Gateway Timeout' in body or 'faultstring' in body and 'Timeout' in body:
            raise SiebelSoapError(
                'Allianz UAT no respondió (Gateway Timeout). '
                'Verifique whitelist IP / disponibilidad del servicio.',
                details={'body': body[:2000]},
            )
        return body

    def _parse_call_response(self, soap_body: str) -> dict[str, Any]:
        try:
            root = etree.fromstring(soap_body.encode('utf-8'))
        except etree.XMLSyntaxError:
            # Some gateways return JSON faults.
            raise SiebelSoapError(f'Respuesta Allianz no es XML: {soap_body[:400]}')

        fault = root.find(f'.//{{{SOAP_NS}}}Fault')
        if fault is not None:
            faultstring = _child_text(fault, 'faultstring') or _text(fault)
            raise SiebelSoapError(f'SOAP Fault Allianz: {faultstring or soap_body[:300]}')

        return_nodes = root.xpath(
            '//*[local-name()="return"]',
        )
        raw_return = ''
        if return_nodes:
            raw_return = ''.join(return_nodes[0].itertext()).strip()
        if not raw_return:
            # Sometimes the ChargeResponse is inlined without <return>.
            raw_return = soap_body

        # Unescape HTML entities if the string was XML-escaped instead of CDATA.
        if '&lt;ChargeResponse' in raw_return or '&lt;chargeresponse' in raw_return.lower():
            raw_return = html.unescape(raw_return)

        charge_match = re.search(
            r'(<ChargeResponse[\s\S]*?</ChargeResponse>)',
            raw_return,
            flags=re.IGNORECASE,
        )
        if not charge_match:
            # Business error payloads sometimes return plain text / Error tags.
            error_match = re.search(
                r'<Error[^>]*>([\s\S]*?)</Error>|<Message>([\s\S]*?)</Message>',
                raw_return,
                flags=re.IGNORECASE,
            )
            if error_match:
                msg = (error_match.group(1) or error_match.group(2) or '').strip()
                raise SiebelBusinessError(msg or 'Error de negocio Allianz', code='ALLIANZ')
            raise SiebelSoapError(
                'No se encontró ChargeResponse en la respuesta Allianz.',
                details={'snippet': raw_return[:800]},
            )

        charge_xml = charge_match.group(1)
        try:
            charge = etree.fromstring(charge_xml.encode('utf-8'))
        except etree.XMLSyntaxError as exc:
            raise SiebelSoapError(f'ChargeResponse inválido: {exc}') from exc

        error_code = _child_text(charge, 'ErrorCode') or _child_text(charge, 'ReturnCode')
        error_msg = _child_text(charge, 'ErrorMessage') or _child_text(charge, 'ReturnText')
        if error_code and error_code not in ('0', '00', ''):
            raise SiebelBusinessError(
                error_msg or 'Error de negocio Allianz',
                code=error_code,
            )

        vehicle = charge.find('VehicleDetails')
        vehicle_details = {}
        if vehicle is not None:
            vehicle_details = {
                'brand': _child_text(vehicle, 'Brand'),
                'class': _child_text(vehicle, 'Class'),
                'type': _child_text(vehicle, 'Type'),
                'version': _child_text(vehicle, 'Version'),
                'year': _child_text(vehicle, 'VehicleYear'),
                'insured_value': _child_text(vehicle, 'InsuredValue'),
                'protection_device': _child_text(vehicle, 'ProtectionDevice'),
            }

        packages: list[dict[str, Any]] = []
        for package_el in charge.findall('Package'):
            payments = {}
            for payment_el in package_el.findall('Payment'):
                pid = _child_text(payment_el, 'PaymentId').upper()
                payments[pid] = _to_decimal(_child_text(payment_el, 'PremiumValue'))

            coverages = []
            for cov in package_el.findall('Coverage'):
                coverages.append({
                    'coverage_id': _child_text(cov, 'CoverageId'),
                    'name': _child_text(cov, 'CoverageName'),
                    'insured_value': _child_text(cov, 'InsuredValue'),
                    'deductible': _child_text(cov, 'Deductible'),
                })

            package_id = _child_text(package_el, 'PackageId')
            package_name = _child_text(package_el, 'PackageName')
            annual = payments.get('ANUAL')
            monthly = payments.get('MENSUAL')
            packages.append({
                'package_id': package_id,
                'package_name': package_name,
                'product_id': package_id,
                'product_name': package_name or f'Paquete {package_id}',
                'brand': 'Allianz',
                'logo': 'allianz',
                'payments': {
                    'annual': annual,
                    'monthly': monthly,
                    'semestral': payments.get('SEMESTRAL'),
                    'trimestral': payments.get('TRIMESTRAL'),
                },
                'prices': {
                    'emission': annual,
                    'emission_local': annual,
                    'gross': annual,
                    'gross_local': annual,
                    'unit': monthly,
                    'net': annual,
                    'net_local': annual,
                    'currency': 'COP',
                    'currency_local': 'COP',
                },
                'coverages': coverages,
            })

        if not packages:
            raise SiebelBusinessError(
                'Allianz no retornó paquetes para los datos del vehículo.',
                code='NO_PACKAGES',
            )

        return {
            'quotation_number': _child_text(charge, 'QuotationNumber'),
            'quotation_date': _child_text(charge, 'QuotationDate'),
            'effective_date': _child_text(charge, 'EffectiveDate'),
            'term_date': _child_text(charge, 'TermDate'),
            'risk_type_desc': _child_text(charge, 'RiskTypeDesc'),
            'vehicle_details': vehicle_details,
            'packages': packages,
            'raw_charge_xml': charge_xml,
        }

    def _mock_quote(self, payload: dict[str, Any]) -> dict[str, Any]:
        plate = (payload.get('vehicle_plate') or 'XXX000').upper()
        packages = [
            {
                'package_id': '8',
                'package_name': 'Todo Riesgo',
                'product_id': '8',
                'product_name': 'Todo Riesgo',
                'brand': 'Allianz',
                'logo': 'allianz',
                'payments': {
                    'annual': Decimal('2450000'),
                    'monthly': Decimal('220000'),
                    'semestral': Decimal('1280000'),
                    'trimestral': Decimal('670000'),
                },
                'prices': {
                    'emission': Decimal('2450000'),
                    'emission_local': Decimal('2450000'),
                    'gross': Decimal('2450000'),
                    'gross_local': Decimal('2450000'),
                    'unit': Decimal('220000'),
                    'net': Decimal('2450000'),
                    'net_local': Decimal('2450000'),
                    'currency': 'COP',
                    'currency_local': 'COP',
                },
                'coverages': [
                    {
                        'coverage_id': '1',
                        'name': 'Responsabilidad Civil Extracontractual',
                        'insured_value': '4000000000.00',
                        'deductible': '0.00',
                    },
                    {
                        'coverage_id': '2',
                        'name': 'Pérdida Parcial por Daños de Mayor Cuantía',
                        'insured_value': '80000000.00',
                        'deductible': '0.00',
                    },
                    {
                        'coverage_id': '7',
                        'name': 'Asistencia',
                        'insured_value': '0.00',
                        'deductible': '0.00',
                    },
                ],
            },
            {
                'package_id': '5',
                'package_name': 'Sin Hurto',
                'product_id': '5',
                'product_name': 'Sin Hurto',
                'brand': 'Allianz',
                'logo': 'allianz',
                'payments': {
                    'annual': Decimal('1890000'),
                    'monthly': Decimal('170000'),
                    'semestral': Decimal('990000'),
                    'trimestral': Decimal('520000'),
                },
                'prices': {
                    'emission': Decimal('1890000'),
                    'emission_local': Decimal('1890000'),
                    'gross': Decimal('1890000'),
                    'gross_local': Decimal('1890000'),
                    'unit': Decimal('170000'),
                    'net': Decimal('1890000'),
                    'net_local': Decimal('1890000'),
                    'currency': 'COP',
                    'currency_local': 'COP',
                },
                'coverages': [
                    {
                        'coverage_id': '1',
                        'name': 'Responsabilidad Civil Extracontractual',
                        'insured_value': '4000000000.00',
                        'deductible': '0.00',
                    },
                    {
                        'coverage_id': '7',
                        'name': 'Asistencia',
                        'insured_value': '0.00',
                        'deductible': '0.00',
                    },
                ],
            },
        ]
        IntegrationCallLog.objects.create(
            service_name=self.service_name,
            operation='call',
            status=IntegrationCallLog.Status.SUCCESS,
            request_payload={'mock': True, 'payload': payload},
            response_payload={'mock': True, 'packages_count': len(packages)},
            error_message='',
            duration_ms=5,
            correlation_id=self.correlation_id,
            actor_user=self.actor_user,
        )
        return {
            'quotation_number': f'MOCK-{plate}',
            'quotation_date': '',
            'effective_date': payload.get('effective_date') or '',
            'term_date': payload.get('term_date') or '',
            'risk_type_desc': 'Liviano Particular Familiar',
            'vehicle_details': {
                'brand': 'MOCK',
                'type': 'DEMO',
                'year': str(payload.get('vehicle_year') or ''),
                'insured_value': str(payload.get('insured_value') or '0'),
            },
            'packages': packages,
            'raw_charge_xml': '',
        }

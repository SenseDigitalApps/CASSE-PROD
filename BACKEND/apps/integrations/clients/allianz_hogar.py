"""
Allianz Hogar Individual 2013 REST client (quotatePolicy).

mTLS against Apigee endpoint. Same partner certs as Autos Call4.
"""
from __future__ import annotations

import logging
import re
import tempfile
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import requests
from django.conf import settings

from apps.integrations.exceptions import IntegrationError, SiebelBusinessError, SiebelSoapError
from apps.integrations.models import IntegrationCallLog

logger = logging.getLogger(__name__)


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == '':
        return None
    if isinstance(value, Decimal):
        return value
    raw = str(value).strip()
    # "$ 856.245 COP" / "856.245"
    cleaned = re.sub(r'[^\d,.\-]', '', raw)
    if not cleaned:
        return None
    # Colombian thousands with dot: 856.245 -> 856245
    if re.fullmatch(r'\d{1,3}(\.\d{3})+', cleaned):
        cleaned = cleaned.replace('.', '')
    elif ',' in cleaned and '.' in cleaned:
        cleaned = cleaned.replace('.', '').replace(',', '.')
    elif ',' in cleaned:
        cleaned = cleaned.replace(',', '.')
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _is_hogar_mock() -> bool:
    if hasattr(settings, 'ALLIANZ_HOGAR_MOCK'):
        return bool(settings.ALLIANZ_HOGAR_MOCK)
    return bool(getattr(settings, 'ALLIANZ_MOCK', False))


class AllianzHogarClient:
    """mTLS REST client for Allianz Hogar Individual quotatePolicy."""

    service_name = 'allianz_hogar'

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
        if _is_hogar_mock():
            return self._mock_quote(payload)

        body = self.build_request(payload)
        return self._post_json(body)

    def build_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        partner_id = settings.ALLIANZ_PARTNER_ID
        agent_id = settings.ALLIANZ_AGENT_ID
        agent_code = settings.ALLIANZ_AGENT_CODE
        company = settings.ALLIANZ_COMPANY or 'COL'
        if not partner_id or not agent_id or not agent_code:
            raise IntegrationError(
                'Integración Allianz Hogar no configurada. Faltan credenciales de partner.'
            )

        return {
            'authenticationBean': {
                'operationTypeCode': payload.get('operation_type_code', 'TA'),
                'productCode': int(payload.get('product_code') or settings.ALLIANZ_HOGAR_PRODUCT_CODE),
            },
            'operationHeadersBean': {
                'agentCode': str(agent_code),
                'agentId': str(agent_id),
                'company': str(company),
                'partnerId': str(partner_id),
            },
            'transactionNumber': str(payload.get('transaction_number') or 'CASSE'),
            'fechaEfecto': int(payload['effective_date']),
            'formaPago': payload.get('payment_frequency', 'A'),
            'holderDocType': payload.get('holder_doc_type', 'C'),
            'holderDocNumber': str(payload['holder_doc_number']),
            'isHolderOwner': payload.get('is_holder_owner', 'S'),
            'ownerDocNumber': payload.get('owner_doc_number', '') or '',
            'ownerDocType': payload.get('owner_doc_type', '') or '',
            'categoriaDeRiesgo': str(payload.get('risk_category', '3')),
            'codLocalidad': int(str(payload.get('locality_dane_code', '11001'))),
            'direccion': payload['address'],
            'restoDireccion': payload.get('address_extra', '') or '',
            'resto2': payload.get('address_extra2', '') or '',
            'valorEdificio': int(Decimal(str(payload.get('building_value') or 0))),
            'valorContenido': int(Decimal(str(payload.get('contents_value') or 0))),
            'valorHurto': int(Decimal(str(payload.get('theft_value') or 0))),
            'valorTodoRiesgo': int(Decimal(str(payload.get('all_risk_value') or 0))),
            'asegurarMascota': payload.get('pet_coverage', 'NO') or 'NO',
            'anoConstruccion': int(payload['construction_year']),
            'numeroTotalDePisos': int(payload.get('total_floors', 1)),
            'pisoUbicacionApto': int(payload.get('apartment_floor', 1)),
            'numeroSotanos': int(payload.get('basements', 0)),
            'areaTotal': int(payload.get('area_sqm', 50)),
            'cap': int(payload.get('cap') or getattr(settings, 'ALLIANZ_HOGAR_CAP', 0) or 0),
            'tipoDeConstruccion': str(payload.get('construction_type', '3')),
            'tipoDeVivienda': str(payload.get('housing_type', '2')),
        }

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

        self._temp_dir = tempfile.TemporaryDirectory(prefix='allianz_hogar_mtls_')
        cert_file = Path(self._temp_dir.name) / 'cert.pem'
        key_file = Path(self._temp_dir.name) / 'key.pem'
        cert_file.write_bytes(cert.public_bytes(Encoding.PEM))
        key_file.write_bytes(
            key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        )
        self._cert_files = (str(cert_file), str(key_file))
        return self._cert_files

    def _post_json(self, body: dict[str, Any]) -> dict[str, Any]:
        endpoint = settings.ALLIANZ_HOGAR_ENDPOINT_URL
        timeout = int(getattr(settings, 'ALLIANZ_HOGAR_TIMEOUT', 45))
        started = time.monotonic()
        error_message = ''
        response_payload: dict[str, Any] = {}
        status = IntegrationCallLog.Status.SUCCESS
        try:
            response = requests.post(
                endpoint,
                json=body,
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
                cert=self._cert_tuple(),
                timeout=(min(15, timeout), timeout),
            )
            duration_ms = int((time.monotonic() - started) * 1000)
            raw_text = response.text or ''
            try:
                data = response.json() if raw_text else {}
            except ValueError:
                data = {'raw': raw_text[:2000]}

            if response.status_code >= 400:
                status = IntegrationCallLog.Status.ERROR
                message = (
                    (data.get('message') if isinstance(data, dict) else None)
                    or (data.get('data') if isinstance(data, dict) else None)
                    or raw_text[:400]
                )
                error_message = str(message)
                raise SiebelSoapError(
                    f'Allianz Hogar HTTP {response.status_code}: {error_message}',
                    details={'status_code': response.status_code, 'body': data},
                )

            parsed = self._parse_response(data if isinstance(data, dict) else {})
            response_payload = {'quotation_number': parsed.get('quotation_number'), 'packages': len(parsed.get('packages') or [])}
            return parsed
        except (SiebelSoapError, SiebelBusinessError, IntegrationError):
            status = IntegrationCallLog.Status.ERROR
            raise
        except requests.RequestException as exc:
            status = IntegrationCallLog.Status.ERROR
            error_message = str(exc)
            duration_ms = int((time.monotonic() - started) * 1000)
            raise SiebelSoapError(f'Error de red Allianz Hogar: {exc}') from exc
        finally:
            duration_ms = locals().get('duration_ms', int((time.monotonic() - started) * 1000))
            IntegrationCallLog.objects.create(
                service_name=self.service_name,
                operation='quotatePolicy',
                status=status,
                request_payload=_json_safe(body),
                response_payload=_json_safe(response_payload),
                error_message=error_message,
                duration_ms=duration_ms,
                correlation_id=self.correlation_id,
                actor_user=self.actor_user,
            )

    def _parse_response(self, data: dict[str, Any]) -> dict[str, Any]:
        # Success envelope: { success, status, data: { paquetes, ... } }
        # Or flat: { paquetes, quotationNumber, ... }
        payload = data.get('data') if isinstance(data.get('data'), dict) else data

        if data.get('success') is False:
            errors = data.get('errors') or []
            msg = ''
            if errors and isinstance(errors[0], dict):
                msg = errors[0].get('message') or ''
            elif isinstance(data.get('data'), str):
                msg = data['data']
            raise SiebelBusinessError(msg or 'Allianz Hogar rechazó la cotización.')

        errors = payload.get('error') or []
        if errors:
            first = errors[0] if isinstance(errors, list) else errors
            raise SiebelBusinessError(str(first))

        packages_raw = payload.get('paquetes') or payload.get('packages') or []
        packages: list[dict[str, Any]] = []
        for item in packages_raw:
            package_id = str(item.get('packageId') or item.get('package_id') or '')
            name = item.get('packageName') or item.get('package_name') or f'Paquete {package_id}'
            payments_map: dict[str, Decimal | None] = {
                'annual': None,
                'monthly': None,
                'semestral': None,
                'trimestral': None,
            }
            for pay in item.get('payments') or []:
                pid = str(pay.get('paymentId') or pay.get('payment_id') or '').upper()
                amount = _to_decimal(pay.get('premiumValue') or pay.get('premium_value'))
                if pid == 'A':
                    payments_map['annual'] = amount
                elif pid == 'M':
                    payments_map['monthly'] = amount
                elif pid == 'S':
                    payments_map['semestral'] = amount
                elif pid == 'T':
                    payments_map['trimestral'] = amount

            annual = payments_map['annual']
            coverages = []
            for cov in item.get('coverages') or []:
                coverages.append({
                    'coverage_id': str(cov.get('coverageId') or cov.get('coverage_id') or ''),
                    'name': cov.get('coverageName') or cov.get('coverage_name') or '',
                    'insured_value': str(cov.get('insuredValue') or cov.get('insured_value') or ''),
                    'deductible': str(cov.get('deducible') or cov.get('deductible') or ''),
                })

            packages.append({
                'package_id': package_id,
                'package_name': name,
                'product_id': package_id,
                'product_name': name,
                'brand': 'Allianz',
                'logo': 'allianz',
                'payments': payments_map,
                'prices': {
                    'emission': annual,
                    'emission_local': annual,
                    'gross': annual,
                    'gross_local': annual,
                    'unit': payments_map['monthly'],
                    'net': annual,
                    'net_local': annual,
                    'currency': 'COP',
                    'currency_local': 'COP',
                },
                'coverages': coverages,
            })

        return {
            'quotation_number': str(
                payload.get('quotationNumber')
                or payload.get('quotation_number')
                or ''
            ),
            'risk_type_desc': payload.get('riskTypeDesc') or payload.get('risk_type_desc') or '',
            'city': payload.get('ciudad') or '',
            'department': payload.get('departamento') or '',
            'address': payload.get('viaNombre') or payload.get('via_nombre') or '',
            'packages': packages,
        }

    def _mock_quote(self, payload: dict[str, Any]) -> dict[str, Any]:
        building = int(Decimal(str(payload.get('building_value') or 0)))
        contents = int(Decimal(str(payload.get('contents_value') or 0)))
        insured = max(building, contents, 1)
        packages = [
            {
                'package_id': '1',
                'package_name': 'Hogar Básico',
                'product_id': '1',
                'product_name': 'Hogar Básico',
                'brand': 'Allianz',
                'logo': 'allianz',
                'payments': {
                    'annual': Decimal('667571'),
                    'monthly': Decimal('60000'),
                    'semestral': Decimal('350000'),
                    'trimestral': Decimal('180000'),
                },
                'prices': {
                    'emission': Decimal('667571'),
                    'emission_local': Decimal('667571'),
                    'gross': Decimal('667571'),
                    'gross_local': Decimal('667571'),
                    'unit': Decimal('60000'),
                    'net': Decimal('667571'),
                    'net_local': Decimal('667571'),
                    'currency': 'COP',
                    'currency_local': 'COP',
                },
                'coverages': [
                    {
                        'coverage_id': '1',
                        'name': 'Incendio',
                        'insured_value': f'{insured}.00',
                        'deductible': '0.00',
                    },
                    {
                        'coverage_id': '5',
                        'name': 'Terremoto',
                        'insured_value': f'{insured}.00',
                        'deductible': '2.00',
                    },
                    {
                        'coverage_id': '3',
                        'name': 'Asistencia Domiciliaria',
                        'insured_value': '1.00',
                        'deductible': '0.00',
                    },
                ],
            },
            {
                'package_id': '2',
                'package_name': 'Hogar Esencial',
                'product_id': '2',
                'product_name': 'Hogar Esencial',
                'brand': 'Allianz',
                'logo': 'allianz',
                'payments': {
                    'annual': Decimal('856245'),
                    'monthly': Decimal('78000'),
                    'semestral': Decimal('450000'),
                    'trimestral': Decimal('230000'),
                },
                'prices': {
                    'emission': Decimal('856245'),
                    'emission_local': Decimal('856245'),
                    'gross': Decimal('856245'),
                    'gross_local': Decimal('856245'),
                    'unit': Decimal('78000'),
                    'net': Decimal('856245'),
                    'net_local': Decimal('856245'),
                    'currency': 'COP',
                    'currency_local': 'COP',
                },
                'coverages': [
                    {
                        'coverage_id': '1',
                        'name': 'Incendio',
                        'insured_value': f'{insured}.00',
                        'deductible': '0.00',
                    },
                    {
                        'coverage_id': '2',
                        'name': 'Responsabilidad Civil Extracontractual- Propiedad',
                        'insured_value': '800000000.00',
                        'deductible': '0.00',
                    },
                    {
                        'coverage_id': '7',
                        'name': 'Daños por Agua',
                        'insured_value': f'{insured}.00',
                        'deductible': '0.00',
                    },
                ],
            },
        ]
        IntegrationCallLog.objects.create(
            service_name=self.service_name,
            operation='quotatePolicy',
            status=IntegrationCallLog.Status.SUCCESS,
            request_payload={'mock': True, 'payload': _json_safe(payload)},
            response_payload={'mock': True, 'packages_count': len(packages)},
            error_message='',
            duration_ms=5,
            correlation_id=self.correlation_id,
            actor_user=self.actor_user,
        )
        return {
            'quotation_number': f"MOCK-H-{payload.get('holder_doc_number', '0')}",
            'risk_type_desc': {
                '1': 'Propietario que arrienda',
                '2': 'Inquilino',
                '3': 'Propietario que habita',
            }.get(str(payload.get('risk_category', '3')), ''),
            'city': '',
            'department': '',
            'address': payload.get('address', ''),
            'packages': packages,
        }

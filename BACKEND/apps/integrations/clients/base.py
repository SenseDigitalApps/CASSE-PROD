"""
Base SOAP client for Siebel / Universal Assistance webservices.

Uses zeep with WS-Security UsernameToken authentication as defined in DIS035.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from django.conf import settings
from lxml import etree
import requests
from zeep import Client, Settings as ZeepSettings
from zeep.helpers import serialize_object
from zeep.plugins import HistoryPlugin
from zeep.transports import Transport
from zeep.wsse.username import UsernameToken

from apps.integrations.constants import WSDL_FILES
from apps.integrations.exceptions import SiebelBusinessError, SiebelSoapError
from apps.integrations.models import IntegrationCallLog

logger = logging.getLogger(__name__)

WSDL_DIR = Path(__file__).resolve().parent.parent / 'wsdl'


def _json_safe(value: Any) -> Any:
    """Strip zeep internals and ensure JSON-serializable output."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
            if not str(key).startswith('_')
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _serialize_for_log(value: Any) -> Any:
    """Convert zeep objects to JSON-serializable structures."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return _json_safe([_serialize_for_log(item) for item in value])
    if isinstance(value, dict):
        return _json_safe({str(k): _serialize_for_log(v) for k, v in value.items()})
    try:
        return _json_safe(serialize_object(value))
    except Exception:
        return str(value)


class SiebelSoapClient:
    """Reusable SOAP client with logging and WS-Security."""

    service_name: str = 'base'
    binding_name: str = ''

    def __init__(
        self,
        *,
        wsdl_filename: str | None = None,
        actor_user=None,
        correlation_id: str = '',
    ):
        self.wsdl_filename = wsdl_filename
        self.actor_user = actor_user
        self.correlation_id = correlation_id
        self._history = HistoryPlugin()
        self._client: Client | None = None
        self._service = None

    @property
    def wsdl_path(self) -> Path:
        if not self.wsdl_filename:
            raise ValueError('wsdl_filename is required')
        return WSDL_DIR / self.wsdl_filename

    @property
    def client(self) -> Client:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _build_client(self) -> Client:
        timeout = getattr(settings, 'UA_SOAP_TIMEOUT', 30)
        # Enforce connect + read timeouts. Keep default User-Agent (Cloudflare
        # in front of Siebel QA may treat custom agents differently).
        session = requests.Session()
        transport = Transport(
            session=session,
            timeout=(min(10, timeout), timeout),
            operation_timeout=timeout,
        )
        zeep_settings = ZeepSettings(strict=False, xml_huge_tree=True)

        return Client(
            wsdl=str(self.wsdl_path),
            transport=transport,
            settings=zeep_settings,
            wsse=UsernameToken(
                settings.UA_SIEBEL_USERNAME,
                settings.UA_SIEBEL_PASSWORD,
            ),
            plugins=[self._history],
        )

    @property
    def service(self):
        if self._service is None:
            if self.binding_name:
                self._service = self.client.create_service(
                    self.binding_name,
                    settings.UA_SIEBEL_ENDPOINT_URL,
                )
            else:
                self._service = self.client.service
        return self._service

    def call(self, operation: str, **kwargs) -> Any:
        """Execute a SOAP operation with logging and error handling."""
        started = time.monotonic()
        status = IntegrationCallLog.Status.SUCCESS
        error_message = ''
        result = None

        try:
            service_method = getattr(self.service, operation)
            result = service_method(**kwargs)
            self._validate_business_response(result)
            return result
        except SiebelBusinessError as exc:
            status = IntegrationCallLog.Status.ERROR
            error_message = str(exc)
            raise
        except Exception as exc:
            status = IntegrationCallLog.Status.ERROR
            error_message = str(exc)
            logger.exception('SOAP call failed: %s.%s', self.service_name, operation)
            raise SiebelSoapError(
                f'Error en llamada SOAP {self.service_name}.{operation}: {exc}',
                details={'operation': operation},
            ) from exc
        finally:
            duration_ms = int((time.monotonic() - started) * 1000)
            self._log_call(
                operation=operation,
                status=status,
                request_data=kwargs,
                response_data=result,
                error_message=error_message,
                duration_ms=duration_ms,
            )

    def _validate_business_response(self, result: Any) -> None:
        """Check common Siebel error fields in responses."""
        if result is None:
            return

        data = _serialize_for_log(result)
        if not isinstance(data, dict):
            return

        error_code = (
            data.get('ErrorCode')
            or data.get('Error_spcCode')
            or data.get('ErrCodeCons')
            or data.get('ErrorCodeAnulacion')
        )
        error_msg = (
            data.get('ErrorMsg')
            or data.get('Error_spcMessage')
            or data.get('ErrMsgCons')
            or data.get('ErrorMsgAnulacion')
        )

        if error_code and str(error_code) not in ('00', '0', ''):
            raise SiebelBusinessError(
                error_msg or 'Error de negocio en Siebel',
                code=str(error_code),
                details=data,
            )

    def _log_call(
        self,
        *,
        operation: str,
        status: str,
        request_data: dict,
        response_data: Any,
        error_message: str,
        duration_ms: int,
    ) -> None:
        request_body = None
        response_body = None

        try:
            if self._history.last_sent:
                request_body = etree.tostring(
                    self._history.last_sent['envelope'], encoding='unicode'
                )
        except (IndexError, KeyError, TypeError):
            pass

        try:
            if self._history.last_received:
                response_body = etree.tostring(
                    self._history.last_received['envelope'], encoding='unicode'
                )
        except (IndexError, KeyError, TypeError):
            pass

        IntegrationCallLog.objects.create(
            service_name=self.service_name,
            operation=operation,
            status=status,
            request_payload={
                'params': _serialize_for_log(request_data),
                'soap_envelope': request_body,
            },
            response_payload={
                'result': _serialize_for_log(response_data),
                'soap_envelope': response_body,
            },
            error_message=error_message,
            duration_ms=duration_ms,
            correlation_id=self.correlation_id,
            actor_user=self.actor_user,
        )

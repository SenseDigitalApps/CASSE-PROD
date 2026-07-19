"""Constants for Universal Assistance Siebel integration."""

SIEBEL_ERROR_OK = '00'
SIEBEL_ERROR_FAIL = '11'

SERVICE_LEAD_COTIZADOR = 'lead_cotizador'
SERVICE_VOUCHER = 'voucher'
SERVICE_QUERY_PORTAL = 'query_voucher_portal'
SERVICE_SEND_REPORT = 'send_report'
SERVICE_ENVIAR_MAIL = 'enviar_voucher_mail'
SERVICE_RETIRE_LEAD = 'retire_lead'

WSDL_FILES = {
    SERVICE_LEAD_COTIZADOR: 'lead_cotizador.wsdl',
    SERVICE_VOUCHER: 'operaciones_voucher.wsdl',
    SERVICE_QUERY_PORTAL: 'query_voucher_portal.wsdl',
    SERVICE_SEND_REPORT: 'send_report.wsdl',
    SERVICE_ENVIAR_MAIL: 'enviar_voucher_mail.wsdl',
    SERVICE_RETIRE_LEAD: 'lead_service_retire.wsdl',
}

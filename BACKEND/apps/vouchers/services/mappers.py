"""Document type mapping between CASSE users and UA catalogs."""
from __future__ import annotations

USER_ID_TYPE_TO_UA = {
    'CC': 'DNI',
    'CE': 'CI',
    'PASSPORT': 'Pasaporte',
    'TI': 'LE',
    'NIT': 'Otros',
}


def map_user_id_type_to_ua(id_type: str) -> str:
    normalized = (id_type or '').strip().upper()
    return USER_ID_TYPE_TO_UA.get(normalized, id_type or 'DNI')

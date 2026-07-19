"""Helpers for resolving catalog values to Siebel codes."""
from apps.catalogs.models import CatalogEntry, DestinationMapping


def resolve_destination(*, ui_code: str | None = None, siebel_value: str | None = None) -> str:
    """
    Resolve a destination to the Siebel value.

    Accepts either a UI code (e.g. EUROPA), a catalog code/label already in
    Siebel format (e.g. Europa), or a direct Siebel value.
    """
    if siebel_value:
        return siebel_value

    if not ui_code:
        raise ValueError('Se requiere ui_code o siebel_value para el destino')

    normalized = ui_code.strip()
    mapping = DestinationMapping.objects.filter(ui_code=normalized, is_active=True).first()
    if mapping:
        return mapping.siebel_value

    mapping = DestinationMapping.objects.filter(
        siebel_value=normalized,
        is_active=True,
    ).first()
    if mapping:
        return mapping.siebel_value

    catalog_entry = CatalogEntry.objects.filter(
        catalog_type=CatalogEntry.CatalogType.DESTINATION,
        code=normalized,
        is_active=True,
    ).first()
    if catalog_entry:
        return catalog_entry.code

    raise ValueError(f'Destino no mapeado: {ui_code}')

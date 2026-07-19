"""Seed Universal Assistance catalog data from bundled JSON files."""
import json
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.catalogs.models import CatalogEntry, DestinationMapping

DATA_DIR = Path(__file__).resolve().parent.parent.parent / 'data'


class Command(BaseCommand):
    help = 'Import UA/Siebel catalog LOVs and destination mappings from JSON seed files'

    def handle(self, *args, **options):
        catalogs_path = DATA_DIR / 'catalogs.json'
        mappings_path = DATA_DIR / 'destination_mappings.json'

        if not catalogs_path.exists():
            self.stderr.write(self.style.ERROR(f'Missing {catalogs_path}'))
            return

        with open(catalogs_path, encoding='utf-8') as f:
            catalogs = json.load(f)

        created_entries = 0
        updated_entries = 0
        for catalog_type, items in catalogs.items():
            if catalog_type not in CatalogEntry.CatalogType.values:
                self.stdout.write(self.style.WARNING(f'Skipping unknown type: {catalog_type}'))
                continue
            for order, item in enumerate(items):
                _, created = CatalogEntry.objects.update_or_create(
                    catalog_type=catalog_type,
                    code=item['code'],
                    defaults={
                        'label': item['label'],
                        'is_active': True,
                        'sort_order': order,
                    },
                )
                if created:
                    created_entries += 1
                else:
                    updated_entries += 1

        created_mappings = 0
        updated_mappings = 0
        if mappings_path.exists():
            with open(mappings_path, encoding='utf-8') as f:
                mappings = json.load(f)
            for order, mapping in enumerate(mappings):
                _, created = DestinationMapping.objects.update_or_create(
                    ui_code=mapping['ui_code'],
                    defaults={
                        'ui_label': mapping['ui_label'],
                        'siebel_value': mapping['siebel_value'],
                        'is_active': True,
                        'sort_order': order,
                    },
                )
                if created:
                    created_mappings += 1
                else:
                    updated_mappings += 1

        self.stdout.write(self.style.SUCCESS(
            f'Catalog entries: {created_entries} created, {updated_entries} updated. '
            f'Destination mappings: {created_mappings} created, {updated_mappings} updated.'
        ))

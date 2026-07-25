# Generated manually for Allianz AutoQuote models

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('quotes', '0003_travelquote_commercial_assignment'),
    ]

    operations = [
        migrations.CreateModel(
            name='AutoQuote',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('affiliate_type', models.CharField(choices=[('INDIVIDUAL', 'No asociado'), ('CAVIPETROL', 'Asociado Cavipetrol')], default='INDIVIDUAL', max_length=16)),
                ('product_code', models.CharField(default='1243', max_length=8)),
                ('vehicle_plate', models.CharField(max_length=12)),
                ('vehicle_year', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('fasecolda_code', models.CharField(blank=True, default='', max_length=20)),
                ('risk_type', models.CharField(default='L0008', max_length=16)),
                ('is_new_vehicle', models.BooleanField(default=False)),
                ('in_dealership', models.BooleanField(default=False)),
                ('insured_value', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('circulation_dane_code', models.CharField(blank=True, default='11001', max_length=10)),
                ('circulation_city_name', models.CharField(blank=True, default='', max_length=120)),
                ('holder_doc_type', models.CharField(default='C', max_length=4)),
                ('holder_doc_number', models.CharField(max_length=32)),
                ('holder_born_date', models.DateField()),
                ('holder_sex', models.CharField(default='M', max_length=1)),
                ('is_holder_driver', models.BooleanField(default=True)),
                ('is_holder_owner', models.BooleanField(default=True)),
                ('effective_date', models.DateField()),
                ('term_date', models.DateField()),
                ('allianz_quotation_number', models.CharField(blank=True, default='', max_length=64)),
                ('vehicle_brand', models.CharField(blank=True, default='', max_length=80)),
                ('vehicle_line', models.CharField(blank=True, default='', max_length=120)),
                ('vehicle_version', models.CharField(blank=True, default='', max_length=200)),
                ('contact_first_name', models.CharField(blank=True, default='', max_length=100)),
                ('contact_last_name', models.CharField(blank=True, default='', max_length=100)),
                ('contact_email', models.EmailField(blank=True, default='', max_length=254)),
                ('contact_phone', models.CharField(blank=True, default='', max_length=40)),
                ('status', models.CharField(choices=[('DRAFT', 'Borrador'), ('QUOTED', 'Cotizada'), ('EXPIRED', 'Expirada'), ('SELECTED', 'Plan seleccionado'), ('ASSIGNED', 'Asignada a comercial'), ('CONVERTED', 'Convertida')], db_index=True, default='DRAFT', max_length=16)),
                ('app_reference', models.CharField(blank=True, db_index=True, default='', max_length=32)),
                ('insurer_reference', models.CharField(blank=True, default='', max_length=64)),
                ('insurer_name', models.CharField(blank=True, default='', max_length=100)),
                ('assigned_commercial_name', models.CharField(blank=True, default='', max_length=255)),
                ('assigned_commercial_email', models.EmailField(blank=True, default='', max_length=254)),
                ('assigned_commercial_title', models.CharField(blank=True, default='', max_length=120)),
                ('client_notified_at', models.DateTimeField(blank=True, null=True)),
                ('commercial_notified_at', models.DateTimeField(blank=True, null=True)),
                ('selected_at', models.DateTimeField(blank=True, null=True)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='auto_quotes', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Cotización de autos',
                'verbose_name_plural': 'Cotizaciones de autos',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='AutoQuotePackage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('package_id', models.CharField(db_index=True, max_length=32)),
                ('product_id_siebel', models.CharField(db_index=True, max_length=32)),
                ('product_name', models.CharField(max_length=200)),
                ('brand', models.CharField(blank=True, default='Allianz', max_length=100)),
                ('logo', models.CharField(blank=True, default='allianz', max_length=100)),
                ('price_emission', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('price_emission_local', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('price_gross', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('price_gross_local', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('price_unit', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('price_net', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('price_net_local', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('premium_annual', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('premium_monthly', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('premium_semestral', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('premium_trimestral', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('currency', models.CharField(blank=True, default='COP', max_length=10)),
                ('currency_local', models.CharField(blank=True, default='COP', max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('quote', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='products', to='quotes.autoquote')),
            ],
            options={
                'verbose_name': 'Paquete autos cotizado',
                'verbose_name_plural': 'Paquetes autos cotizados',
                'ordering': ['price_emission_local', 'product_name'],
            },
        ),
        migrations.CreateModel(
            name='AutoQuoteCoverage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('coverage_id', models.CharField(blank=True, default='', max_length=32)),
                ('name', models.CharField(max_length=300)),
                ('visible_name', models.CharField(blank=True, default='', max_length=300)),
                ('unit', models.CharField(blank=True, default='', max_length=50)),
                ('value', models.CharField(blank=True, default='', max_length=200)),
                ('deductible', models.CharField(blank=True, default='', max_length=64)),
                ('sort_order', models.PositiveSmallIntegerField(default=0)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attributes', to='quotes.autoquotepackage')),
            ],
            options={
                'verbose_name': 'Cobertura autos',
                'verbose_name_plural': 'Coberturas autos',
                'ordering': ['sort_order', 'name'],
            },
        ),
        migrations.AddField(
            model_name='autoquote',
            name='selected_product',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='selected_in_quotes', to='quotes.autoquotepackage'),
        ),
        migrations.AddIndex(
            model_name='autoquote',
            index=models.Index(fields=['user', 'status'], name='quotes_auto_user_id_0f2c0a_idx'),
        ),
        migrations.AddIndex(
            model_name='autoquote',
            index=models.Index(fields=['user', 'expires_at'], name='quotes_auto_user_id_7c1e2b_idx'),
        ),
        migrations.AddIndex(
            model_name='autoquote',
            index=models.Index(fields=['vehicle_plate'], name='quotes_auto_vehicle_9d4a1c_idx'),
        ),
        migrations.AddIndex(
            model_name='autoquotepackage',
            index=models.Index(fields=['quote', 'package_id'], name='quotes_auto_quote_i_3b8f2d_idx'),
        ),
    ]

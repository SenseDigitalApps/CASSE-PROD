# Generated manually for commercial assignment fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('quotes', '0002_quotepassenger'),
    ]

    operations = [
        migrations.AddField(
            model_name='travelquote',
            name='app_reference',
            field=models.CharField(blank=True, db_index=True, default='', max_length=32),
        ),
        migrations.AddField(
            model_name='travelquote',
            name='assigned_commercial_email',
            field=models.EmailField(blank=True, default='', max_length=254),
        ),
        migrations.AddField(
            model_name='travelquote',
            name='assigned_commercial_name',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='travelquote',
            name='assigned_commercial_title',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
        migrations.AddField(
            model_name='travelquote',
            name='client_notified_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='travelquote',
            name='commercial_notified_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='travelquote',
            name='insurer_name',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='travelquote',
            name='insurer_reference',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='travelquote',
            name='selected_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='travelquote',
            name='status',
            field=models.CharField(
                choices=[
                    ('DRAFT', 'Borrador'),
                    ('QUOTED', 'Cotizada'),
                    ('EXPIRED', 'Expirada'),
                    ('SELECTED', 'Plan seleccionado'),
                    ('ASSIGNED', 'Asignada a comercial'),
                    ('CONVERTED', 'Convertida'),
                ],
                db_index=True,
                default='DRAFT',
                max_length=16,
            ),
        ),
    ]

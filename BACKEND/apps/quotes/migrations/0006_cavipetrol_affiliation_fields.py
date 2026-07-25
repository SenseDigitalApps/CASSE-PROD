# Generated manually for Cavipetrol affiliation commercial fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('quotes', '0005_rename_quotes_auto_user_id_0f2c0a_idx_quotes_auto_user_id_0d06b8_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='autoquote',
            name='affiliation_number',
            field=models.CharField(blank=True, default='', max_length=40),
        ),
        migrations.AddField(
            model_name='autoquote',
            name='payment_form',
            field=models.CharField(blank=True, default='', max_length=40),
        ),
        migrations.AddField(
            model_name='autoquote',
            name='paying_company',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
        migrations.AddField(
            model_name='travelquote',
            name='affiliation_number',
            field=models.CharField(blank=True, default='', max_length=40),
        ),
        migrations.AddField(
            model_name='travelquote',
            name='payment_form',
            field=models.CharField(blank=True, default='', max_length=40),
        ),
        migrations.AddField(
            model_name='travelquote',
            name='paying_company',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
    ]

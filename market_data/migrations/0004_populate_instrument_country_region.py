
"""
Data Migration: Populate country and economic region mapping for all instruments
Per Phase 1 Master Architecture requirements:
"Har instrument ke base/quote country, currency aur economic region mapping."
"""
from django.db import migrations


def update_mappings(apps, schema_editor):
    Instrument = apps.get_model('market_data', 'Instrument')

    mappings = {
        # Forex Majors
        'EURUSD': {'base_country': 'Eurozone', 'quote_country': 'United States', 'base_region': 'Europe', 'quote_region': 'North America'},
        'GBPUSD': {'base_country': 'United Kingdom', 'quote_country': 'United States', 'base_region': 'Europe', 'quote_region': 'North America'},
        'USDJPY': {'base_country': 'United States', 'quote_country': 'Japan', 'base_region': 'North America', 'quote_region': 'Asia'},
        'USDCHF': {'base_country': 'United States', 'quote_country': 'Switzerland', 'base_region': 'North America', 'quote_region': 'Europe'},
        'AUDUSD': {'base_country': 'Australia', 'quote_country': 'United States', 'base_region': 'Oceania', 'quote_region': 'North America'},
        'USDCAD': {'base_country': 'United States', 'quote_country': 'Canada', 'base_region': 'North America', 'quote_region': 'North America'},
        'NZDUSD': {'base_country': 'New Zealand', 'quote_country': 'United States', 'base_region': 'Oceania', 'quote_region': 'North America'},

        # Forex Crosses
        'EURGBP': {'base_country': 'Eurozone', 'quote_country': 'United Kingdom', 'base_region': 'Europe', 'quote_region': 'Europe'},
        'EURJPY': {'base_country': 'Eurozone', 'quote_country': 'Japan', 'base_region': 'Europe', 'quote_region': 'Asia'},
        'GBPJPY': {'base_country': 'United Kingdom', 'quote_country': 'Japan', 'base_region': 'Europe', 'quote_region': 'Asia'},

        # Commodities
        'XAUUSD': {'base_country': 'Global', 'quote_country': 'United States', 'base_region': 'Global', 'quote_region': 'North America'},
        'XAGUSD': {'base_country': 'Global', 'quote_country': 'United States', 'base_region': 'Global', 'quote_region': 'North America'},
        'USOIL':  {'base_country': 'United States', 'quote_country': 'United States', 'base_region': 'North America', 'quote_region': 'North America'},
        'UKOIL':  {'base_country': 'United Kingdom', 'quote_country': 'United States', 'base_region': 'Europe', 'quote_region': 'North America'},

        # Crypto
        'BTCUSD': {'base_country': 'Global', 'quote_country': 'United States', 'base_region': 'Global', 'quote_region': 'North America'},
        'ETHUSD': {'base_country': 'Global', 'quote_country': 'United States', 'base_region': 'Global', 'quote_region': 'North America'},
        'BNBUSD': {'base_country': 'Global', 'quote_country': 'United States', 'base_region': 'Global', 'quote_region': 'North America'},
        'SOLUSD': {'base_country': 'Global', 'quote_country': 'United States', 'base_region': 'Global', 'quote_region': 'North America'},

        # Indices
        'US30':   {'base_country': 'United States', 'quote_country': 'United States', 'base_region': 'North America', 'quote_region': 'North America'},
        'SPX500': {'base_country': 'United States', 'quote_country': 'United States', 'base_region': 'North America', 'quote_region': 'North America'},
        'NAS100': {'base_country': 'United States', 'quote_country': 'United States', 'base_region': 'North America', 'quote_region': 'North America'},
        'GER40':  {'base_country': 'Germany', 'quote_country': 'Eurozone', 'base_region': 'Europe', 'quote_region': 'Europe'},
        'UK100':  {'base_country': 'United Kingdom', 'quote_country': 'United Kingdom', 'base_region': 'Europe', 'quote_region': 'Europe'},
    }

    for symbol, fields in mappings.items():
        Instrument.objects.filter(symbol=symbol).update(**fields)


class Migration(migrations.Migration):
    dependencies = [
        ('market_data', '0003_datasourcehealth_instrument_base_country_and_more'),
    ]

    operations = [
        migrations.RunPython(update_mappings, migrations.RunPython.noop),
    ]

"""
Data Migration: Seed initial instruments and market sessions
Run: python manage.py migrate
"""
from django.db import migrations


def seed_instruments(apps, schema_editor):
    Instrument = apps.get_model('market_data', 'Instrument')

    instruments = [
        # Forex Majors
        {'symbol': 'EURUSD', 'name': 'Euro / US Dollar',          'market_type': 'forex',     'base': 'EUR', 'quote': 'USD', 'pip_value': 0.0001},
        {'symbol': 'GBPUSD', 'name': 'British Pound / US Dollar', 'market_type': 'forex',     'base': 'GBP', 'quote': 'USD', 'pip_value': 0.0001},
        {'symbol': 'USDJPY', 'name': 'US Dollar / Japanese Yen',  'market_type': 'forex',     'base': 'USD', 'quote': 'JPY', 'pip_value': 0.01},
        {'symbol': 'USDCHF', 'name': 'US Dollar / Swiss Franc',   'market_type': 'forex',     'base': 'USD', 'quote': 'CHF', 'pip_value': 0.0001},
        {'symbol': 'AUDUSD', 'name': 'Australian Dollar / USD',   'market_type': 'forex',     'base': 'AUD', 'quote': 'USD', 'pip_value': 0.0001},
        {'symbol': 'USDCAD', 'name': 'US Dollar / Canadian Dollar','market_type': 'forex',    'base': 'USD', 'quote': 'CAD', 'pip_value': 0.0001},
        {'symbol': 'NZDUSD', 'name': 'New Zealand Dollar / USD',  'market_type': 'forex',     'base': 'NZD', 'quote': 'USD', 'pip_value': 0.0001},

        # Forex Crosses
        {'symbol': 'EURGBP', 'name': 'Euro / British Pound',      'market_type': 'forex',     'base': 'EUR', 'quote': 'GBP', 'pip_value': 0.0001},
        {'symbol': 'EURJPY', 'name': 'Euro / Japanese Yen',       'market_type': 'forex',     'base': 'EUR', 'quote': 'JPY', 'pip_value': 0.01},
        {'symbol': 'GBPJPY', 'name': 'British Pound / Yen',       'market_type': 'forex',     'base': 'GBP', 'quote': 'JPY', 'pip_value': 0.01},

        # Commodities
        {'symbol': 'XAUUSD', 'name': 'Gold / US Dollar',          'market_type': 'commodity', 'base': 'XAU', 'quote': 'USD', 'pip_value': 0.01},
        {'symbol': 'XAGUSD', 'name': 'Silver / US Dollar',        'market_type': 'commodity', 'base': 'XAG', 'quote': 'USD', 'pip_value': 0.001},
        {'symbol': 'USOIL',  'name': 'Crude Oil (WTI)',            'market_type': 'commodity', 'base': 'OIL', 'quote': 'USD', 'pip_value': 0.01},
        {'symbol': 'UKOIL',  'name': 'Brent Crude Oil',           'market_type': 'commodity', 'base': 'OIL', 'quote': 'USD', 'pip_value': 0.01},

        # Crypto
        {'symbol': 'BTCUSD', 'name': 'Bitcoin / US Dollar',       'market_type': 'crypto',    'base': 'BTC', 'quote': 'USD', 'pip_value': 1.0},
        {'symbol': 'ETHUSD', 'name': 'Ethereum / US Dollar',      'market_type': 'crypto',    'base': 'ETH', 'quote': 'USD', 'pip_value': 0.01},
        {'symbol': 'BNBUSD', 'name': 'BNB / US Dollar',           'market_type': 'crypto',    'base': 'BNB', 'quote': 'USD', 'pip_value': 0.01},
        {'symbol': 'SOLUSD', 'name': 'Solana / US Dollar',        'market_type': 'crypto',    'base': 'SOL', 'quote': 'USD', 'pip_value': 0.001},

        # Indices
        {'symbol': 'US30',   'name': 'Dow Jones Industrial Avg',  'market_type': 'index',     'base': 'US30','quote': 'USD', 'pip_value': 1.0},
        {'symbol': 'SPX500', 'name': 'S&P 500 Index',             'market_type': 'index',     'base': 'SPX', 'quote': 'USD', 'pip_value': 0.1},
        {'symbol': 'NAS100', 'name': 'NASDAQ 100 Index',          'market_type': 'index',     'base': 'NAS', 'quote': 'USD', 'pip_value': 0.1},
        {'symbol': 'GER40',  'name': 'DAX 40 (Germany)',          'market_type': 'index',     'base': 'GER', 'quote': 'EUR', 'pip_value': 0.1},
        {'symbol': 'UK100',  'name': 'FTSE 100 (UK)',             'market_type': 'index',     'base': 'UK',  'quote': 'GBP', 'pip_value': 0.1},
    ]

    for data in instruments:
        Instrument.objects.get_or_create(symbol=data['symbol'], defaults=data)


def seed_sessions(apps, schema_editor):
    MarketSession = apps.get_model('market_data', 'MarketSession')

    sessions = [
        {'session': 'sydney',   'open_time': '21:00', 'close_time': '06:00'},
        {'session': 'tokyo',    'open_time': '00:00', 'close_time': '09:00'},
        {'session': 'london',   'open_time': '07:00', 'close_time': '16:00'},
        {'session': 'new_york', 'open_time': '12:00', 'close_time': '21:00'},
        {'session': 'overlap',  'open_time': '12:00', 'close_time': '16:00'},
    ]

    for data in sessions:
        MarketSession.objects.get_or_create(session=data['session'], defaults=data)


class Migration(migrations.Migration):
    dependencies = [
        ('market_data', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_instruments, migrations.RunPython.noop),
        migrations.RunPython(seed_sessions,    migrations.RunPython.noop),
    ]

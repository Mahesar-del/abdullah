from django.core.management.base import BaseCommand
from accounts.models import LinkedBrokerAccount

class Command(BaseCommand):
    help = 'Seeds default linked paper trading account'

    def handle(self, *args, **options):
        account, created = LinkedBrokerAccount.objects.get_or_create(
            account_number='TS-PAPER-1001',
            defaults={
                'name': 'Primary Paper Trader (Auto)',
                'broker_type': 'PAPER',
                'server': 'TradeSense-Simulation',
                'is_paper': True,
                'balance': 10000.00,
                'equity': 10000.00,
                'currency': 'USD',
                'is_active': True,
                'auto_trade_enabled': True,
                'max_risk_pct': 1.0,
                'min_confidence': 70.0,
                'max_open_trades': 5,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created default linked account: {account.name}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Default account already exists: {account.name}"))

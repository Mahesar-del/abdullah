"""
TradeSense - MetaApi Cloud Bridge Service
Connects directly to Exness / MT5 broker servers via MetaApi Cloud
without requiring MetaTrader 5 software installed on the local system.
"""

import os
import asyncio
import logging
from decimal import Decimal
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)

class MetaApiCloudBridge:
    @classmethod
    def get_token(cls):
        """
        Retrieves MetaApi token from environment or settings.
        """
        token = os.environ.get('METAAPI_TOKEN') or getattr(settings, 'METAAPI_TOKEN', '')
        return str(token).strip()

    @classmethod
    def sync_account_balance(cls, broker_account, token: str = None) -> dict:
        """
        Synchronizes live balance & equity from Exness/MT5 broker via MetaApi Cloud.
        """
        token = token or cls.get_token()
        if not token:
            return {'success': False, 'error': 'MetaApi Token not configured.'}

        try:
            return asyncio.run(cls._async_sync_balance(broker_account, token))
        except Exception as e:
            logger.error(f"[MetaApi] Sync error for {broker_account.account_number}: {e}")
            return {'success': False, 'error': str(e)}

    @classmethod
    async def _async_sync_balance(cls, broker_account, token: str) -> dict:
        from metaapi_cloud_sdk import MetaApi
        api = MetaApi(token)
        
        account_api = api.metatrader_account_api
        accounts = await account_api.get_accounts()

        # Find or register account
        login_str = str(broker_account.account_number).strip()
        matched = None
        for acc in accounts:
            if str(acc.login).strip() == login_str:
                matched = acc
                break

        if not matched:
            # Register new account with MetaApi
            logger.info(f"[MetaApi] Registering account {login_str} on server {broker_account.server}...")
            matched = await account_api.create_account({
                'name': broker_account.name or f"Exness-{login_str}",
                'type': 'cloud',
                'login': login_str,
                'password': broker_account.api_secret or '',
                'server': broker_account.server,
                'platform': 'mt5' if 'MT5' in broker_account.server.upper() or broker_account.broker_type in ('EXNESS', 'MT5') else 'mt4',
                'magic': 100001
            })

        # Ensure account is deployed
        if matched.state != 'DEPLOYED':
            logger.info(f"[MetaApi] Deploying account {matched.id}...")
            await matched.deploy()
            await matched.wait_deployed()

        connection = matched.get_rpc_connection()
        await connection.connect()
        await connection.wait_synchronized()

        account_info = await connection.get_account_information()
        balance = round(float(account_info.get('balance', 0.0)), 2)
        equity = round(float(account_info.get('equity', balance)), 2)

        broker_account.balance = Decimal(str(balance))
        broker_account.equity = Decimal(str(equity))
        broker_account.last_sync_at = timezone.now()
        broker_account.save(update_fields=['balance', 'equity', 'last_sync_at', 'updated_at'])

        logger.info(f"[MetaApi] Successfully synced live balance from Exness: ${balance:,.2f}")
        return {
            'success': True,
            'balance': balance,
            'equity': equity,
            'currency': account_info.get('currency', 'USD'),
            'server': account_info.get('server', broker_account.server)
        }

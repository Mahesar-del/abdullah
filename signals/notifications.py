"""
Alert & Notification Dispatcher — Hardened Production Version
Implements Checklist Section 7 & 8:
- Telegram Bot API delivery (BUY/SELL signals, high-impact event warnings, TP/SL hit resolution).
- Official WhatsApp Business API (Meta Cloud API primary, Twilio REST fallback).
- Audit trail logging into AlertDelivery database model with true delivery states:
  'DELIVERED' (verified API response), 'FAILED' (network/HTTP error), 'SKIPPED' (credentials unconfigured or category disabled).
- Zero mock credentials presented as live.
- Respects NotificationPreference category/channel toggle rules.
"""
import requests
import logging
import time
from datetime import datetime
from django.conf import settings
from django.utils import timezone as dj_tz
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def _is_mock_credential(val: Optional[str]) -> bool:
    """Detect unconfigured, missing, or placeholder credentials."""
    if not val:
        return True
    s = str(val).strip().upper()
    return (
        s == ''
        or 'MOCK' in s
        or 'YOUR_' in s
        or 'PLACEHOLDER' in s
        or 'CHANGE_ME' in s
        or s == 'NONE'
    )


class TelegramNotifier:
    """
    Sends signals, warnings, and outcome events to a Telegram Channel or Group.
    Per Checklist Section 7.
    """
    def __init__(self):
        self.bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '') or ''
        self.chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', '') or ''
        self.proxy_url = getattr(settings, 'TELEGRAM_PROXY_URL', '') or ''
        self.api_base = getattr(settings, 'TELEGRAM_API_BASE', 'https://api.telegram.org') or 'https://api.telegram.org'

    @property
    def is_configured(self) -> bool:
        return not _is_mock_credential(self.bot_token) and not _is_mock_credential(self.chat_id)

    def send_signal(self, signal) -> bool:
        """Dispatches confirmed BUY/SELL alert with entry, SL, TP1/2/3, confidence, and confluence."""
        if getattr(signal, 'direction', None) == 'WAIT':
            return False

        icon = '🟢 BUY' if signal.direction == 'BUY' else '🔴 SELL'
        text = (
            f"⚡ *TRADESENSE PRO — CONFIRMED SIGNAL* ⚡\n\n"
            f"📊 *Asset:* `{signal.instrument.symbol}` | *TF:* `{signal.timeframe}`\n"
            f"🎯 *Direction:* {icon} ({getattr(signal, 'strength', 'NORMAL')})\n"
            f"📈 *Confidence:* `{signal.confidence_score}%` | *R:R:* `{signal.risk_reward}`\n\n"
            f"🔹 *Entry Price:* `{signal.entry_price}`\n"
            f"🛑 *Stop Loss:* `{signal.stop_loss}`\n"
            f"✅ *Take Profit 1:* `{signal.take_profit_1}`\n"
        )
        if getattr(signal, 'take_profit_2', None):
            text += f"✅ *Take Profit 2:* `{signal.take_profit_2}`\n"
        if getattr(signal, 'take_profit_3', None):
            text += f"✅ *Take Profit 3:* `{signal.take_profit_3}`\n"

        warnings = getattr(signal, 'warnings', None) or []
        if warnings:
            text += f"\n⚠️ *Warnings:*\n• " + "\n• ".join(str(w) for w in warnings)

        return self._dispatch(
            title=f"Trade Alert {signal.direction} {signal.instrument.symbol}",
            text=text,
            category='SIGNAL',
            signal=signal
        )

    def send_event_warning(self, title: str, currency: str, impact: str, event_time) -> bool:
        """Dispatches high-impact economic or central bank event blackout warnings."""
        time_str = event_time.strftime('%Y-%m-%d %H:%M UTC') if hasattr(event_time, 'strftime') else str(event_time)
        text = (
            f"🚨 *HIGH-IMPACT NEWS CAUTION WINDOW* 🚨\n\n"
            f"📌 *Event:* `{title}`\n"
            f"💱 *Currency:* `{currency}` | *Impact:* `{impact}`\n"
            f"🕒 *Scheduled Time:* `{time_str}`\n\n"
            f"⚠️ *Trading Rule:* Signals on affected pairs are paused/restricted during event blackout."
        )
        return self._dispatch(
            title=f"News Blackout Warning: {currency} {title[:30]}",
            text=text,
            category='NEWS_WARNING',
            signal=None
        )

    def send_signal_outcome(self, signal, outcome: str, pnl_pips: float, exit_price: float) -> bool:
        """Dispatches TP/SL hit resolution alerts."""
        icon = '🏆' if outcome in ('WIN', 'HIT_TP') else '🛑'
        sym = getattr(signal.instrument, 'symbol', 'UNKNOWN') if hasattr(signal, 'instrument') else 'UNKNOWN'
        text = (
            f"{icon} *TRADE RESOLUTION: {sym}* {icon}\n\n"
            f"📊 *Signal ID:* `#{getattr(signal, 'id', 'N/A')}` | *Direction:* `{getattr(signal, 'direction', 'N/A')}`\n"
            f"🎯 *Outcome:* `{outcome}`\n"
            f"💵 *Exit Price:* `{exit_price}`\n"
            f"📈 *PnL (Pips):* `{pnl_pips:+.1f} pips`\n"
        )
        return self._dispatch(
            title=f"Signal Resolution {sym}: {outcome}",
            text=text,
            category='OUTCOME',
            signal=signal
        )

    def send_invalidation(self, signal, reason: str) -> bool:
        """Dispatches signal invalidation notice."""
        sym = getattr(signal.instrument, 'symbol', 'UNKNOWN') if hasattr(signal, 'instrument') else 'UNKNOWN'
        text = (
            f"⚠️ *SIGNAL INVALIDATED: {sym}* ⚠️\n\n"
            f"📊 *Signal ID:* `#{getattr(signal, 'id', 'N/A')}`\n"
            f"Reason: {reason}\n"
        )
        return self._dispatch(
            title=f"Signal Invalidation {sym}",
            text=text,
            category='INVALIDATION',
            signal=signal
        )

    def _dispatch(self, title: str, text: str, category: str = 'SIGNAL', signal=None, max_retries: int = 1) -> bool:
        # Check NotificationPreference toggle
        try:
            from signals.models import NotificationPreference
            if not NotificationPreference.is_enabled('TELEGRAM', category):
                self._record_delivery(
                    signal=signal,
                    channel='TELEGRAM',
                    category=category,
                    title=title,
                    message=text,
                    status='SKIPPED',
                    error_message=f"Category '{category}' is disabled in Telegram preferences"
                )
                return False
        except Exception as e:
            logger.debug(f"NotificationPreference check error: {e}")

        payload = {'chat_id': str(self.chat_id), 'text': text, 'parse_mode': 'Markdown'}

        if not self.is_configured:
            # Audit log clearly records SKIPPED — zero fake DELIVERED records
            self._record_delivery(
                signal=signal,
                channel='TELEGRAM',
                category=category,
                title=title,
                message=text,
                status='SKIPPED',
                error_message="Telegram credentials not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing or placeholder)",
                payload=payload
            )
            return False

        # Live dispatch with proxy support and retry
        proxies = {'http': self.proxy_url, 'https': self.proxy_url} if self.proxy_url else None
        api_url = f"{self.api_base.rstrip('/')}/bot{self.bot_token}/sendMessage"
        success = False
        error_msg = ""
        provider_msg_id = ""

        for attempt in range(max_retries + 1):
            try:
                resp = requests.post(api_url, json=payload, timeout=5, proxies=proxies)
                if resp.status_code == 200:
                    success = True
                    try:
                        res_json = resp.json()
                        provider_msg_id = str(res_json.get('result', {}).get('message_id', ''))
                    except Exception:
                        pass
                    break
                else:
                    error_msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    time.sleep(0.3)
            except Exception as e:
                error_msg = str(e)
                time.sleep(0.3)

        self._record_delivery(
            signal=signal,
            channel='TELEGRAM',
            category=category,
            title=title,
            message=text,
            status='DELIVERED' if success else 'FAILED',
            error_message=error_msg,
            payload=payload,
            provider_message_id=provider_msg_id
        )
        return success

    def _record_delivery(self, signal, channel: str, category: str, title: str, message: str,
                         status: str, error_message: str = "", payload: dict = None,
                         provider_message_id: str = ""):
        try:
            from signals.models import AlertDelivery
            AlertDelivery.objects.create(
                signal=signal,
                channel=channel,
                category=category,
                recipient=str(self.chat_id or 'UNSET'),
                title=title,
                message=message,
                status=status,
                error_message=error_message or "",
                response_payload=payload or {},
                provider='TELEGRAM_BOT',
                provider_message_id=provider_message_id or "",
                delivered_at=dj_tz.now() if status == 'DELIVERED' else None,
                status_updated_at=dj_tz.now()
            )
        except Exception as e:
            logger.debug(f"Could not persist AlertDelivery log: {e}")


class WhatsAppNotifier:
    """
    Official WhatsApp Business Platform API integration (Meta Cloud API primary, Twilio REST fallback).
    Per Checklist Section 8.
    """
    def __init__(self):
        # Meta Cloud API credentials
        self.meta_token = getattr(settings, 'META_WA_TOKEN', '') or ''
        self.meta_phone_id = getattr(settings, 'META_WA_PHONE_NUMBER_ID', '') or ''
        self.meta_recipient = getattr(settings, 'META_WA_RECIPIENT', '') or ''
        self.meta_version = getattr(settings, 'META_WA_API_VERSION', 'v21.0') or 'v21.0'

        # Twilio fallback credentials
        self.twilio_account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '') or ''
        self.twilio_auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', '') or ''
        self.twilio_from = getattr(settings, 'TWILIO_FROM_WHATSAPP', '') or ''
        self.twilio_to = getattr(settings, 'TWILIO_TO_WHATSAPP', '') or ''

    @property
    def has_meta(self) -> bool:
        return (
            not _is_mock_credential(self.meta_token)
            and not _is_mock_credential(self.meta_phone_id)
            and not _is_mock_credential(self.meta_recipient)
        )

    @property
    def has_twilio(self) -> bool:
        return (
            not _is_mock_credential(self.twilio_account_sid)
            and not _is_mock_credential(self.twilio_auth_token)
            and not _is_mock_credential(self.twilio_from)
            and not _is_mock_credential(self.twilio_to)
        )

    @property
    def is_configured(self) -> bool:
        return self.has_meta or self.has_twilio

    def send_signal(self, signal) -> bool:
        if getattr(signal, 'direction', None) == 'WAIT':
            return False

        icon = '🟢 BUY' if signal.direction == 'BUY' else '🔴 SELL'
        sym = getattr(signal.instrument, 'symbol', 'UNKNOWN') if hasattr(signal, 'instrument') else 'UNKNOWN'
        message = (
            f"🚨 *TRADE ALERT: {sym}* 🚨\n\n"
            f"{icon} @ {signal.entry_price}\n"
            f"TF: {signal.timeframe} | Conf: {signal.confidence_score}%\n"
            f"🛑 SL: {signal.stop_loss} | 🎯 TP: {signal.take_profit_1}\n"
            f"🤖 _TradeSense Pro AI Engine_"
        )
        return self._dispatch(
            title=f"WhatsApp Trade Alert {sym}",
            text=message,
            category='SIGNAL',
            signal=signal
        )

    def send_event_warning(self, title: str, currency: str, impact: str, event_time) -> bool:
        time_str = event_time.strftime('%Y-%m-%d %H:%M UTC') if hasattr(event_time, 'strftime') else str(event_time)
        message = f"⚠️ *HIGH-IMPACT EVENT ALERT*\n{currency}: {title} @ {time_str}"
        return self._dispatch(
            title=f"WhatsApp Event Alert: {currency} {title[:30]}",
            text=message,
            category='NEWS_WARNING',
            signal=None
        )

    def send_signal_outcome(self, signal, outcome: str, pnl_pips: float, exit_price: float) -> bool:
        sym = getattr(signal.instrument, 'symbol', 'UNKNOWN') if hasattr(signal, 'instrument') else 'UNKNOWN'
        message = (
            f"🏆 *SIGNAL OUTCOME: {sym}*\n"
            f"Status: {outcome}\n"
            f"Exit: {exit_price} | PnL: {pnl_pips:+.1f} pips"
        )
        return self._dispatch(
            title=f"WhatsApp Outcome {sym}: {outcome}",
            text=message,
            category='OUTCOME',
            signal=signal
        )

    def _dispatch(self, title: str, text: str, category: str = 'SIGNAL', signal=None) -> bool:
        # Check NotificationPreference toggle
        try:
            from signals.models import NotificationPreference
            if not NotificationPreference.is_enabled('WHATSAPP', category):
                self._record_delivery(
                    signal=signal,
                    category=category,
                    title=title,
                    message=text,
                    status='SKIPPED',
                    error_message=f"Category '{category}' is disabled in WhatsApp preferences"
                )
                return False
        except Exception as e:
            logger.debug(f"NotificationPreference check error: {e}")

        # If Meta WhatsApp Business Cloud API is available, try it first
        if self.has_meta:
            return self._dispatch_meta(title, text, category, signal)

        # Fallback to Twilio
        if self.has_twilio:
            return self._dispatch_twilio(title, text, category, signal)

        # Unconfigured credentials: record SKIPPED
        self._record_delivery(
            signal=signal,
            category=category,
            title=title,
            message=text,
            status='SKIPPED',
            error_message="WhatsApp credentials not configured (neither Meta Cloud API nor Twilio credentials present)",
            provider='UNCONFIGURED'
        )
        return False

    def _dispatch_meta(self, title: str, text: str, category: str, signal) -> bool:
        url = f"https://graph.facebook.com/{self.meta_version}/{self.meta_phone_id}/messages"
        headers = {
            'Authorization': f'Bearer {self.meta_token}',
            'Content-Type': 'application/json'
        }
        payload = {
            'messaging_product': 'whatsapp',
            'recipient_type': 'individual',
            'to': self.meta_recipient,
            'type': 'text',
            'text': {'preview_url': False, 'body': text}
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=6)
            if resp.status_code in (200, 201):
                data = resp.json()
                msg_id = data.get('messages', [{}])[0].get('id', '')
                self._record_delivery(
                    signal=signal,
                    category=category,
                    title=title,
                    message=text,
                    status='DELIVERED',
                    provider='META_CLOUD',
                    provider_message_id=msg_id,
                    payload=data
                )
                return True
            else:
                self._record_delivery(
                    signal=signal,
                    category=category,
                    title=title,
                    message=text,
                    status='FAILED',
                    error_message=f"Meta Cloud API {resp.status_code}: {resp.text[:200]}",
                    provider='META_CLOUD'
                )
                return False
        except Exception as e:
            self._record_delivery(
                signal=signal,
                category=category,
                title=title,
                message=text,
                status='FAILED',
                error_message=f"Meta Cloud API error: {str(e)}",
                provider='META_CLOUD'
            )
            return False

    def _dispatch_twilio(self, title: str, text: str, category: str, signal) -> bool:
        from_num = self.twilio_from if self.twilio_from.startswith('whatsapp:') else f'whatsapp:{self.twilio_from}'
        to_num = self.twilio_to if self.twilio_to.startswith('whatsapp:') else f'whatsapp:{self.twilio_to}'
        try:
            from twilio.rest import Client
            client = Client(self.twilio_account_sid, self.twilio_auth_token)
            msg = client.messages.create(body=text, from_=from_num, to=to_num)
            self._record_delivery(
                signal=signal,
                category=category,
                title=title,
                message=text,
                status='DELIVERED',
                provider='TWILIO',
                provider_message_id=getattr(msg, 'sid', '')
            )
            return True
        except Exception as e:
            self._record_delivery(
                signal=signal,
                category=category,
                title=title,
                message=text,
                status='FAILED',
                error_message=f"Twilio error: {str(e)}",
                provider='TWILIO'
            )
            return False

    def _record_delivery(self, signal, category: str, title: str, message: str, status: str,
                         error_message: str = "", provider: str = "WHATSAPP",
                         provider_message_id: str = "", payload: dict = None):
        try:
            from signals.models import AlertDelivery
            recipient = self.meta_recipient or self.twilio_to or 'UNSET'
            AlertDelivery.objects.create(
                signal=signal,
                channel='WHATSAPP',
                category=category,
                recipient=recipient,
                title=title,
                message=message,
                status=status,
                error_message=error_message or "",
                provider=provider,
                provider_message_id=provider_message_id or "",
                response_payload=payload or {},
                delivered_at=dj_tz.now() if status == 'DELIVERED' else None,
                status_updated_at=dj_tz.now()
            )
        except Exception as e:
            logger.debug(f"Could not persist AlertDelivery log: {e}")


# Global Notifier Singletons
telegram_notifier = TelegramNotifier()
whatsapp_notifier = WhatsAppNotifier()
notifier = whatsapp_notifier

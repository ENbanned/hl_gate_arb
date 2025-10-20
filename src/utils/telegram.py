import asyncio
from datetime import datetime

import httpx

from config.settings import settings
from utils.logging import get_logger


log = get_logger(__name__)


class TelegramNotifier:
  
  def __init__(self):
    self.token = settings.telegram_bot_token
    self.chat_id = settings.telegram_chat_id
    self.url = f"https://api.telegram.org/bot{self.token}/sendMessage"
    self.client = httpx.AsyncClient(timeout=10.0)
  
  
  async def send(self, message: str, silent: bool = False):
    try:
      await self.client.post(
        self.url,
        json={
          "chat_id": self.chat_id,
          "text": message,
          "parse_mode": "HTML",
          "disable_notification": silent,
        },
      )
      log.debug("telegram_message_sent", message=message[:100])
    except Exception as e:
      log.warning("telegram_send_failed", error=str(e))
  
  
  async def position_opened(
    self,
    coin: str,
    direction: str,
    net_spread: float,
    size_usd: float,
    leverage: int,
    expected_profit: float,
  ):
    arrow = "→" if direction == "gate_to_hl" else "←"
    msg = (
      f"🟢 <b>Position Opened</b>\n\n"
      f"Coin: <b>{coin}</b>\n"
      f"Direction: Gate {arrow} Hyperliquid\n"
      f"Net Spread: <b>{net_spread:.2f}%</b>\n"
      f"Size: ${size_usd:.0f} (Leverage: {leverage}x)\n"
      f"Expected Profit: <b>${expected_profit:.2f}</b>\n"
      f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )
    await self.send(msg)
  
  
  async def position_closed(
    self,
    coin: str,
    entry_spread: float,
    realized_pnl: float,
    funding_cost: float,
    net_pnl: float,
    duration_minutes: float,
    reason: str,
  ):
    emoji = "🔴" if net_pnl < 0 else "🟢"
    msg = (
      f"{emoji} <b>Position Closed</b>\n\n"
      f"Coin: <b>{coin}</b>\n"
      f"Entry Spread: {entry_spread:.2f}%\n"
      f"Realized P&L: <b>${realized_pnl:.2f}</b>\n"
      f"Funding Cost: ${funding_cost:.2f}\n"
      f"Net P&L: <b>${net_pnl:.2f}</b>\n"
      f"Duration: {duration_minutes:.1f} min\n"
      f"Reason: {reason}\n"
      f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )
    await self.send(msg)
  
  
  async def error_alert(self, error_type: str, details: str):
    msg = (
      f"⚠️ <b>Error Alert</b>\n\n"
      f"Type: {error_type}\n"
      f"Details: {details}\n"
      f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )
    await self.send(msg)
  
  
  async def daily_summary(
    self,
    trades_count: int,
    total_pnl: float,
    win_rate: float,
    balance: float,
  ):
    emoji = "📊"
    msg = (
      f"{emoji} <b>Daily Summary</b>\n\n"
      f"Trades: {trades_count}\n"
      f"Total P&L: <b>${total_pnl:.2f}</b>\n"
      f"Win Rate: {win_rate:.1f}%\n"
      f"Balance: <b>${balance:.2f}</b>\n"
      f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )
    await self.send(msg, silent=True)
  
  
  async def close(self):
    await self.client.aclose()


notifier = TelegramNotifier()
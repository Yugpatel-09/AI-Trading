# TradeForge Background Workers (`services/workers`)

Celery / Redis background task runners responsible for:
- End-of-day broker ledger reconciliation
- Asynchronous backtesting job execution
- Nightly model drift calculations
- Daily 08:30 AM IST broker token expiry reminders via SMS / Email / Telegram

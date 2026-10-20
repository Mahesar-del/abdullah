# Trading Safety Operations

## Accessing account controls

Broker account, automation, trade, and balance APIs require an authenticated Django staff session. Sign in through `/admin/login/`, then return to the dashboard. Create the first operator with `python manage.py createsuperuser` (use the Render shell for the deployed service). Keep staff accounts limited to operators who are allowed to view broker identifiers and control trading.

## Deploy behavior

Run `python manage.py migrate` during deployment. Migration `accounts.0003` disarms existing automation: it turns the global switch off and clears account authorization/auto-trade flags. It does not close or edit existing execution records. New accounts also start with automation disabled. Paper automation requires an explicit operator authorization.

The service currently rejects live authorization because verified walk-forward reports are not persisted and connected to the go-live gate. Keep that block in place until a reproducible report contains real broker costs, out-of-sample sleeve results, portfolio drawdown and bootstrap statistics, followed by at least 90 days of paper results. Do not fill the gate with placeholder metrics.

## Production configuration

Set a unique generated `SECRET_KEY`, `DEBUG=False`, and the exact deployed hostname in `ALLOWED_HOSTS`. The Render blueprint creates a secret and configures the production hostname. HTTPS redirect, secure session/CSRF cookies, and HSTS are enabled when `DEBUG=False`. Add other origins to `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` only when a separate trusted frontend needs them.

A passing software check does not establish trading profitability. Paper-trade performance net of spread, commission, swap and slippage must be evaluated before considering live execution.

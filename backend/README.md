# RAKJID DataHub Backend

Flask backend for account authentication, password resets, Paystack wallet funding, and SME API plan lookup.

Password reset requires SMTP settings and `PUBLIC_API_URL`.

Wallet top-up uses Paystack initialization, callback verification, and an
idempotent signed webhook. Data and airtime purchase endpoints return `503`
until the account-specific SME purchase API is configured. No routes create
fake balances or transactions.

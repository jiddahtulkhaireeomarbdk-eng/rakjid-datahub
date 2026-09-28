# Setup

## Backend
1. Open `backend/`
2. Create a Python virtual environment.
3. Install:
   `pip install -r requirements.txt`
4. Copy `backend/.env.example` to `backend/.env` and set a unique
   `AUTH_TOKEN_SECRET` (generate one with
   `python -c "import secrets; print(secrets.token_hex(32))"`).
5. Configure the SMTP values and `PUBLIC_API_URL` to enable password-reset email.
6. Start:
   `python app.py`

The backend stores accounts, wallet balances, and transaction history in
`backend/datahub.sqlite3`. The file is created automatically on first start.
To use another database location, set `DATAHUB_DATABASE_PATH` before starting
the backend.

## Deploy backend to Render
1. Push this project to a GitHub repository.
2. In Render, choose **New +** then **Blueprint** and select the repository.
3. Render will use `render.yaml` to create the API service.
4. Set `SME_API_KEY`, `SME_API_BASE_URL`, SMTP settings, and `PUBLIC_API_URL`
   in the Render environment variables. Render generates `AUTH_TOKEN_SECRET`.
   Set `PAYSTACK_SECRET_KEY` to the server secret key from your Paystack
   dashboard (`sk_test_...` for testing or `sk_live_...` after Paystack enables
   live transactions). Never put this key in Flutter or commit it to GitHub.
   For Flutter Web, set `CORS_ALLOWED_ORIGINS` to the exact frontend origin.
5. Confirm `https://your-service.onrender.com/api/health` returns status `ok`.

Wallet top-ups use Paystack hosted checkout and are credited only after the
backend verifies a successful NGN payment. Configure the Paystack webhook URL as
`https://your-api.onrender.com/api/payments/paystack/webhook`.

Data and airtime purchases remain unavailable until the exact SME purchase
endpoints for your provider account are configured. The backend does not
simulate successful payments or purchases.

The Render configuration mounts SQLite at `/var/data`. Keep the persistent disk
enabled; without persistent storage, accounts and wallet history can disappear
when the service is redeployed.

## Flutter
1. Open `flutter_app/`
2. Run `flutter pub get`
3. Run `flutter analyze`
4. Run `flutter run`

For the Play Store release, replace the URL with your deployed Render URL:
`flutter build appbundle --release --dart-define=BACKEND_URL=https://your-service.onrender.com`

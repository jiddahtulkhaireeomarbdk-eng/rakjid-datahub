# Setup

## Backend
1. Open `backend/`
2. Create a Python virtual environment.
3. Install:
   `pip install -r requirements.txt`
4. Copy `.env.example` to `.env`
5. Add your SME API key.
6. Start:
   `python app.py`

The backend now stores accounts, wallet balances, and transaction history in
`backend/datahub.sqlite3`. The file is created automatically on first start.
To use another database location, set `DATAHUB_DATABASE_PATH` before starting
the backend.

## Deploy backend to Render
1. Push this project to a GitHub repository.
2. In Render, choose **New +** then **Blueprint** and select the repository.
3. Render will use `render.yaml` to create the API service.
4. Set `SME_API_KEY` and `SME_API_BASE_URL` in the Render environment variables.
5. Confirm `https://your-service.onrender.com/api/health` returns status `ok`.

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

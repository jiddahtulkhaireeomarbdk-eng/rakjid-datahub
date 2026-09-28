# RAKJID DataHub

mobile app for Nigerian data and airtime vending project.

## Structure
- `flutter_app/` — Flutter mobile application
- `backend/` — Python Flask API and provider integration

## Important
Provider API keys and Paystack secret keys belong only in `backend/.env`.
Never put secrets inside Flutter or commit them to GitHub.

## Provider
The backend is prepared for SME API integration. Live purchases require a funded provider account and valid production credentials.

import os

import requests

BASE_URL = os.getenv("SME_API_BASE_URL", "").rstrip("/")
API_KEY = os.getenv("SME_API_KEY", "")


def headers():
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def get_data_plans():
    if not BASE_URL or not API_KEY:
        return [
            {"id": "mtn-1gb", "network": "MTN", "plan": "1GB", "amount": 350},
            {"id": "glo-2gb", "network": "Glo", "plan": "2GB", "amount": 650},
            {"id": "airtel-3gb", "network": "Airtel", "plan": "3GB", "amount": 900},
            {"id": "mtn-5gb", "network": "MTN", "plan": "5GB", "amount": 1500},
        ]

    response = requests.get(f"{BASE_URL}/data/plans", headers=headers(), timeout=30)
    response.raise_for_status()
    payload = response.json()

    if isinstance(payload, dict):
        for key in ("data", "plans", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return payload

    if isinstance(payload, list):
        return payload

    return []


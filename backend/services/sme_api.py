import os

import requests

BASE_URL = os.getenv("SME_API_BASE_URL", "").rstrip("/")
API_KEY = os.getenv("SME_API_KEY", "")


def headers():
    return {
        "Authorization": f"Token {API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def get_data_plans():
    if not BASE_URL:
        raise RuntimeError("SME API base URL is not configured")

    request_headers = headers() if API_KEY else {"Accept": "application/json"}
    response = requests.get(
        f"{BASE_URL}/dataplans/",
        headers=request_headers,
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    if isinstance(payload, dict):
        for key in ("data", "plans", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        raise ValueError("SME API returned an invalid data plans response")

    if isinstance(payload, list):
        return payload

    raise ValueError("SME API returned an invalid data plans response")


def _purchase(path, payload):
    if not BASE_URL or not API_KEY:
        raise RuntimeError("SME API credentials are not configured")

    response = requests.post(
        f"{BASE_URL}{path}",
        headers=headers(),
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict):
        raise ValueError("SME API returned an invalid purchase response")
    return result


def purchase_data(network_id, plan_id, phone, reference):
    return _purchase("/data/", {
        "network": network_id,
        "data_plan": plan_id,
        "phone": phone,
        "ref": reference,
        "ported_number": "false",
    })


def purchase_airtime(network_id, amount, phone, reference):
    return _purchase("/airtime/", {
        "network": network_id,
        "amount": amount,
        "phone": phone,
        "ref": reference,
        "ported_number": "false",
    })


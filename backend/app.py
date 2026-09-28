import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import smtplib
import time
from decimal import Decimal, InvalidOperation
from email.message import EmailMessage
from urllib.parse import quote

from flask import Flask, Response, g, jsonify, request
from dotenv import load_dotenv
import requests

from database import (
    authenticate_user,
    complete_wallet_funding,
    create_wallet_funding,
    create_user,
    find_user_by_email,
    find_user_by_id,
    get_wallet_funding,
    get_wallet_balance,
    list_transactions,
    reserve_wallet_purchase,
    reset_password_with_token,
    settle_wallet_purchase,
    store_password_reset_token,
)

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

from services.sme_api import get_data_plans, purchase_airtime, purchase_data

app = Flask(__name__)
AUTH_TOKEN_SECRET = os.getenv("AUTH_TOKEN_SECRET", "")
ACCESS_TOKEN_TTL_SECONDS = 60 * 60 * 24
CORS_ALLOWED_ORIGINS = {
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
}

def _encode_token_part(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def create_access_token(user_id):
    payload = _encode_token_part(json.dumps({
        "sub": user_id,
        "exp": int(time.time()) + ACCESS_TOKEN_TTL_SECONDS,
    }, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        AUTH_TOKEN_SECRET.encode("utf-8"),
        payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{payload}.{_encode_token_part(signature)}"


def authenticate_access_token(token):
    if not AUTH_TOKEN_SECRET:
        return None
    try:
        payload, supplied_signature = token.split(".", 1)
        expected_signature = _encode_token_part(hmac.new(
            AUTH_TOKEN_SECRET.encode("utf-8"),
            payload.encode("ascii"),
            hashlib.sha256,
        ).digest())
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return None
        padding = "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload + padding))
        if int(claims.get("exp", 0)) <= int(time.time()):
            return None
        return find_user_by_id(str(claims["sub"]))
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, json.JSONDecodeError):
        return None


@app.before_request
def require_authenticated_user():
    protected_endpoints = {
        "wallet", "wallet_topup", "verify_wallet_topup", "transactions",
        "purchase", "airtime_purchase",
    }
    if request.method == "OPTIONS":
        return None
    if request.endpoint not in protected_endpoints:
        return None
    if not AUTH_TOKEN_SECRET:
        return jsonify({
            "success": False,
            "message": "Authentication is not configured",
        }), 503
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    user = authenticate_access_token(token.strip()) if scheme.lower() == "bearer" else None
    if user is None:
        return jsonify({"success": False, "message": "Authentication required"}), 401
    g.current_user = user
    return None


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin")
    if origin in CORS_ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = (
            "Authorization, Content-Type, X-Paystack-Signature"
        )
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers.add("Vary", "Origin")
    return response


def paystack_secret_key():
    return os.getenv("PAYSTACK_SECRET_KEY", "").strip()


def paystack_request_headers():
    secret_key = paystack_secret_key()
    if not secret_key:
        raise RuntimeError("Paystack is not configured")
    return {
        "Authorization": f"Bearer {secret_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def verify_paystack_transaction(reference):
    response = requests.get(
        f"https://api.paystack.co/transaction/verify/{quote(reference, safe='')}",
        headers=paystack_request_headers(),
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def complete_verified_funding(reference, amount_kobo, currency):
    if currency != "NGN":
        return None
    return complete_wallet_funding(reference, amount_kobo)


def send_password_reset_email(email, token):
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    sender = os.getenv("SMTP_FROM_EMAIL", "").strip()
    public_api_url = os.getenv("PUBLIC_API_URL", "").rstrip("/")
    if not smtp_host or not sender or not public_api_url:
        raise RuntimeError("Password reset email is not configured")

    reset_url = f"{public_api_url}/reset-password?token={quote(token)}"
    message = EmailMessage()
    message["Subject"] = "Reset your RAKJID DataHub password"
    message["From"] = sender
    message["To"] = email
    message.set_content(
        "Use this link to reset your password within 30 minutes:\n\n"
        f"{reset_url}\n\n"
        "If you did not request this, ignore this email."
    )

    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
        if os.getenv("SMTP_STARTTLS", "true").lower() == "true":
            server.starttls()
        if username:
            server.login(username, password)
        server.send_message(message)


def get_wallet_balance_for_user(user_id=None):
    balance = get_wallet_balance(user_id)
    return float(balance) if balance is not None else 0.0


def get_transactions_for_user(user_id=None):
    return list_transactions(user_id)


def _purchase_status(provider_result):
    candidates = [provider_result]
    nested = provider_result.get("data")
    if isinstance(nested, dict):
        candidates.append(nested)

    for candidate in candidates:
        status = candidate.get("status")
        success = candidate.get("success")
        if success is True or status is True:
            return "completed"
        if success is False or status is False:
            return "failed"
        normalized_status = str(status or "").strip().lower()
        if normalized_status in {"success", "successful", "completed"}:
            return "completed"
        if normalized_status in {"failed", "failure", "error", "rejected"}:
            return "failed"
    return "processing"


def _submit_vending_purchase(transaction, reference, provider_request):
    user_id = g.current_user["id"]
    try:
        provider_result = provider_request()
    except RuntimeError:
        settle_wallet_purchase(transaction["id"], user_id, "failed", refund=True)
        return jsonify({
            "success": False,
            "message": "SME API is not configured for purchases",
        }), 503
    except requests.RequestException as exc:
        response = getattr(exc, "response", None)
        status_code = response.status_code if response is not None else None
        if status_code is not None and 400 <= status_code < 500:
            settle_wallet_purchase(transaction["id"], user_id, "failed", refund=True)
            return jsonify({
                "success": False,
                "message": "SME API rejected the purchase; your wallet was refunded",
            }), 502

        app.logger.warning(
            "SME purchase outcome is unknown for reference %s: %s",
            reference,
            exc,
        )
        return jsonify({
            "success": True,
            "status": "processing",
            "reference": reference,
            "message": "Provider confirmation is pending. Do not retry this order; contact support with its reference if it remains pending.",
        }), 202
    except (TypeError, ValueError) as exc:
        app.logger.warning(
            "SME purchase response is invalid for reference %s: %s",
            reference,
            exc,
        )
        return jsonify({
            "success": True,
            "status": "processing",
            "reference": reference,
            "message": "Provider confirmation is pending. Do not retry this order; contact support with its reference if it remains pending.",
        }), 202

    outcome = _purchase_status(provider_result)
    if outcome == "failed":
        settle_wallet_purchase(transaction["id"], user_id, "failed", refund=True)
        return jsonify({
            "success": False,
            "message": "SME API did not complete the purchase; your wallet was refunded",
        }), 502
    if outcome == "processing":
        return jsonify({
            "success": True,
            "status": "processing",
            "reference": reference,
            "message": "Provider confirmation is pending. Do not retry this order; contact support with its reference if it remains pending.",
        }), 202

    settle_wallet_purchase(transaction["id"], user_id, "completed")
    return jsonify({
        "success": True,
        "status": "completed",
        "reference": reference,
        "message": "Purchase completed",
    })


@app.post("/api/auth/signup")
def signup():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", "")).strip()

    if not name or not email or not password:
        return jsonify({
            "success": False,
            "message": "name, email, and password are required",
        }), 400
    if not AUTH_TOKEN_SECRET:
        return jsonify({
            "success": False,
            "message": "Authentication is not configured",
        }), 503

    if find_user_by_email(email) is not None:
        return jsonify({
            "success": False,
            "message": "User already exists",
        }), 409

    user = create_user(name, email, password)

    return jsonify({
        "success": True,
        "message": "Account created successfully",
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "wallet_balance": user["wallet_balance"],
        },
        "access_token": create_access_token(user["id"]),
    }), 201


@app.post("/api/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", "")).strip()

    user = authenticate_user(email, password)
    if user is None:
        return jsonify({
            "success": False,
            "message": "Invalid email or password",
        }), 401
    if not AUTH_TOKEN_SECRET:
        return jsonify({
            "success": False,
            "message": "Authentication is not configured",
        }), 503

    return jsonify({
        "success": True,
        "message": "Login successful",
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "wallet_balance": user["wallet_balance"],
        },
        "access_token": create_access_token(user["id"]),
    })


@app.post("/api/auth/forgot-password")
def forgot_password():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    if not email or len(email) > 254 or "@" not in email:
        return jsonify({
            "success": False,
            "message": "Enter a valid email address",
        }), 400

    if not all(os.getenv(key) for key in ("SMTP_HOST", "SMTP_FROM_EMAIL", "PUBLIC_API_URL")):
        return jsonify({
            "success": False,
            "message": "Password reset email is not configured",
        }), 503

    user = find_user_by_email(email)
    if user is not None:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        store_password_reset_token(
            user["id"], token_hash, int(time.time()) + 30 * 60,
        )
        try:
            send_password_reset_email(email, token)
        except (OSError, smtplib.SMTPException, RuntimeError, ValueError):
            app.logger.exception("Unable to send password reset email")
            return jsonify({
                "success": False,
                "message": "Password reset email could not be sent",
            }), 503

    return jsonify({
        "success": True,
        "message": "If that email has an account, password reset instructions have been sent.",
    })


@app.get("/reset-password")
def reset_password_page():
    token = html.escape(request.args.get("token", ""), quote=True)
    if not token:
        return Response("Reset link is missing or invalid.", status=400, mimetype="text/plain")
    return Response(
        """<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reset password | RAKJID DataHub</title>
<body style="font:16px sans-serif;max-width:420px;margin:48px auto;padding:0 20px">
<h1>Choose a new password</h1><form method="post" action="/api/auth/reset-password">
<input type="hidden" name="token" value=""" + token + """">
<label>New password <input name="password" type="password" minlength="8" required></label>
<p><button type="submit">Reset password</button></p></form></body></html>""",
        mimetype="text/html",
    )


@app.post("/api/auth/reset-password")
def reset_password():
    payload = request.get_json(silent=True) or request.form
    token = str(payload.get("token", "")).strip()
    password = str(payload.get("password", ""))
    if not token or len(password) < 8:
        return jsonify({
            "success": False,
            "message": "A reset token and password of at least 8 characters are required",
        }), 400

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    updated = reset_password_with_token(token_hash, password, int(time.time()))
    if not updated:
        return jsonify({
            "success": False,
            "message": "This password reset link is invalid or has expired",
        }), 400

    if request.is_json:
        return jsonify({"success": True, "message": "Password reset successfully"})
    return Response(
        "Password reset successfully. You can now return to the app and sign in.",
        mimetype="text/plain",
    )


@app.get("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "RAKJID DataHub",
        "provider": "SME API"
    })


@app.get("/")
def index():
    return jsonify({
        "service": "RAKJID DataHub API",
        "status": "ok",
        "health": "/api/health",
    })


@app.get("/api/config")
def config():
    return jsonify({
        "provider": "SME API",
        "networks": {
            "MTN": 1,
            "Glo": 2,
            "9mobile": 3,
            "Airtel": 4
        },
        "baseUrl": os.getenv("SME_API_BASE_URL", "")
    })


@app.get("/api/plans")
def plans():
    try:
        return jsonify({"plans": get_data_plans()})
    except RuntimeError as exc:
        return jsonify({"plans": [], "error": str(exc)}), 503
    except Exception:
        return jsonify({"plans": [], "error": "Unable to load data plans"}), 500


@app.get("/api/wallet")
def wallet():
    return jsonify({
        "balance": get_wallet_balance_for_user(g.current_user["id"]),
        "currency": "NGN",
        "status": "active",
    })


@app.post("/api/wallet/topup")
def wallet_topup():
    secret_key = paystack_secret_key()
    public_api_url = os.getenv("PUBLIC_API_URL", "").rstrip("/")
    if not secret_key or not public_api_url:
        return jsonify({
            "success": False,
            "message": "Paystack and PUBLIC_API_URL must be configured",
        }), 503

    payload = request.get_json(silent=True) or {}
    try:
        amount_naira = Decimal(str(payload.get("amount", "")))
        amount_kobo_decimal = amount_naira * 100
        if (
            not amount_naira.is_finite()
            or amount_naira <= 0
            or amount_kobo_decimal != amount_kobo_decimal.to_integral_value()
        ):
            raise InvalidOperation
        amount_kobo = int(amount_kobo_decimal)
    except (InvalidOperation, ValueError, TypeError):
        return jsonify({
            "success": False,
            "message": "Enter an amount greater than zero with at most two decimal places",
        }), 400

    reference = f"rakjid_{secrets.token_hex(16)}"
    try:
        create_wallet_funding(reference, g.current_user["id"], amount_kobo)
        response = requests.post(
            "https://api.paystack.co/transaction/initialize",
            headers=paystack_request_headers(),
            json={
                "email": g.current_user["email"],
                "amount": amount_kobo,
                "currency": "NGN",
                "reference": reference,
                "callback_url": f"{public_api_url}/api/payments/paystack/callback",
            },
            timeout=20,
        )
        response.raise_for_status()
        result = response.json()
        data = result.get("data") or {}
        if result.get("status") is not True or not data.get("authorization_url"):
            raise ValueError("Paystack did not return a checkout URL")
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        app.logger.warning("Paystack initialization failed for reference %s: %s", reference, exc)
        return jsonify({
            "success": False,
            "message": "Could not start Paystack checkout. Please try again.",
        }), 502

    return jsonify({
        "success": True,
        "message": "Paystack checkout initialized",
        "data": {
            "reference": reference,
            "authorization_url": data["authorization_url"],
        },
    }), 201


@app.post("/api/wallet/topup/verify")
def verify_wallet_topup():
    payload = request.get_json(silent=True) or {}
    reference = str(payload.get("reference", "")).strip()
    funding = get_wallet_funding(reference, g.current_user["id"]) if reference else None
    if funding is None:
        return jsonify({"success": False, "message": "Funding reference not found"}), 404

    if funding["status"] == "completed":
        return jsonify({
            "success": True,
            "status": "completed",
            "balance": get_wallet_balance_for_user(g.current_user["id"]),
        })

    try:
        result = verify_paystack_transaction(reference)
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        app.logger.warning("Paystack verification failed for reference %s: %s", reference, exc)
        return jsonify({"success": False, "message": "Could not verify payment yet"}), 502

    data = result.get("data") or {}
    if (
        result.get("status") is not True
        or data.get("status") != "success"
        or data.get("reference") != reference
        or data.get("amount") != funding["amount_kobo"]
        or data.get("currency") != "NGN"
    ):
        return jsonify({
            "success": False,
            "status": data.get("status", "pending"),
            "message": "Paystack has not confirmed this payment",
        }), 409

    completion = complete_verified_funding(
        reference, funding["amount_kobo"], data["currency"],
    )
    if completion is None:
        return jsonify({"success": False, "message": "Payment details did not match"}), 409
    return jsonify({
        "success": True,
        "status": "completed",
        "balance": completion["balance"],
    })


@app.get("/api/payments/paystack/callback")
def paystack_callback():
    reference = request.args.get("reference", "").strip()
    funding = get_wallet_funding(reference) if reference else None
    if funding is None:
        return Response("Payment reference not found.", status=404, mimetype="text/plain")
    if funding["status"] == "completed":
        return Response("Payment confirmed. Return to the RAKJID DataHub app.", mimetype="text/plain")

    try:
        result = verify_paystack_transaction(reference)
    except (requests.RequestException, RuntimeError, ValueError):
        return Response("Could not verify payment yet. Return to the app and retry verification.", status=502, mimetype="text/plain")

    data = result.get("data") or {}
    if (
        result.get("status") is not True
        or data.get("status") != "success"
        or data.get("reference") != reference
        or data.get("amount") != funding["amount_kobo"]
        or data.get("currency") != "NGN"
    ):
        return Response("Payment is not confirmed. Return to the app to check its status.", status=409, mimetype="text/plain")

    completion = complete_verified_funding(reference, funding["amount_kobo"], data["currency"])
    if completion is None:
        return Response("Payment details did not match.", status=409, mimetype="text/plain")
    return Response("Payment confirmed. Return to the RAKJID DataHub app.", mimetype="text/plain")


@app.post("/api/payments/paystack/webhook")
def paystack_webhook():
    secret_key = paystack_secret_key()
    signature = request.headers.get("x-paystack-signature", "")
    if not secret_key or not signature:
        return jsonify({"success": False}), 401
    expected_signature = hmac.new(
        secret_key.encode("utf-8"), request.get_data(), hashlib.sha512,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        return jsonify({"success": False}), 401

    event = request.get_json(silent=True) or {}
    if event.get("event") != "charge.success":
        return jsonify({"success": True})
    data = event.get("data") or {}
    reference = str(data.get("reference", ""))
    funding = get_wallet_funding(reference) if reference else None
    if funding is None:
        return jsonify({"success": False, "message": "Funding reference not found"}), 404
    if (
        data.get("status") != "success"
        or data.get("amount") != funding["amount_kobo"]
        or data.get("currency") != "NGN"
    ):
        return jsonify({"success": False, "message": "Payment details did not match"}), 400
    if complete_verified_funding(reference, funding["amount_kobo"], data["currency"]) is None:
        return jsonify({"success": False, "message": "Could not apply payment"}), 500
    return jsonify({"success": True})


@app.get("/api/transactions")
def transactions():
    return jsonify({
        "transactions": get_transactions_for_user(g.current_user["id"]),
    })


@app.post("/api/purchase")
def purchase():
    payload = request.get_json(silent=True) or {}
    plan_id = str(payload.get("plan_id", "")).strip()
    phone = str(payload.get("phone", "")).strip()
    digits = phone.removeprefix("+")
    if not plan_id or not digits.isdigit() or not 10 <= len(digits) <= 14:
        return jsonify({
            "success": False,
            "message": "A valid plan and phone number are required",
        }), 400

    try:
        plans_payload = get_data_plans()
    except RuntimeError as exc:
        return jsonify({"success": False, "message": str(exc)}), 503
    except (requests.RequestException, ValueError):
        return jsonify({
            "success": False,
            "message": "Could not load current data plans from SME API",
        }), 502

    plan = next(
        (item for item in plans_payload if str(item.get("id", "")) == plan_id),
        None,
    )
    if plan is None:
        return jsonify({"success": False, "message": "Data plan is no longer available"}), 404

    try:
        amount = Decimal(str(plan.get("price", plan.get("amount", ""))))
        network_id = int(plan["network_id"])
        if not amount.is_finite() or amount <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError, TypeError, KeyError):
        return jsonify({"success": False, "message": "SME API returned invalid plan details"}), 502

    network = str(plan.get("network", "")).strip()
    requested_network = str(payload.get("network", network)).strip()
    if requested_network.casefold() != network.casefold():
        return jsonify({"success": False, "message": "Selected network does not match this plan"}), 400

    reference = f"RAKJID-DATA-{secrets.token_hex(12)}"
    transaction = reserve_wallet_purchase(
        g.current_user["id"],
        f"{network} {plan.get('name', 'data')} data",
        "data",
        amount,
        {"phone": phone, "plan_id": plan_id, "provider_reference": reference},
    )
    if transaction is None:
        return jsonify({"success": False, "message": "Insufficient wallet balance"}), 402

    return _submit_vending_purchase(
        transaction,
        reference,
        lambda: purchase_data(network_id, plan["id"], phone, reference),
    )


@app.post("/api/airtime")
def airtime_purchase():
    payload = request.get_json(silent=True) or {}
    phone = str(payload.get("phone", "")).strip()
    digits = phone.removeprefix("+")
    network = str(payload.get("network", "")).strip()
    network_ids = {"MTN": 1, "Glo": 2, "9mobile": 3, "Airtel": 4}
    if not digits.isdigit() or not 10 <= len(digits) <= 14:
        return jsonify({"success": False, "message": "Enter a valid phone number"}), 400
    network_id = network_ids.get(network)
    if network_id is None:
        return jsonify({"success": False, "message": "Select a valid network"}), 400

    try:
        amount = Decimal(str(payload.get("amount", "")))
        amount_kobo = amount * 100
        if (
            not amount.is_finite()
            or amount <= 0
            or amount_kobo != amount_kobo.to_integral_value()
        ):
            raise InvalidOperation
    except (InvalidOperation, ValueError, TypeError):
        return jsonify({
            "success": False,
            "message": "Enter an amount greater than zero with at most two decimal places",
        }), 400

    reference = f"RAKJID-AIRTIME-{secrets.token_hex(12)}"
    transaction = reserve_wallet_purchase(
        g.current_user["id"],
        f"{network} airtime",
        "airtime",
        amount,
        {"phone": phone, "network": network, "provider_reference": reference},
    )
    if transaction is None:
        return jsonify({"success": False, "message": "Insufficient wallet balance"}), 402

    return _submit_vending_purchase(
        transaction,
        reference,
        lambda: purchase_airtime(network_id, amount, phone, reference),
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

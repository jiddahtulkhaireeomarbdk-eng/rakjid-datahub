import os
from datetime import datetime

from flask import Flask, jsonify, request
from dotenv import load_dotenv

from database import (
    authenticate_user,
    change_wallet_balance,
    create_transaction,
    create_user,
    find_user_by_email,
    find_user_by_id,
    get_wallet_balance,
    list_transactions,
)
from services.sme_api import get_data_plans

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

app = Flask(__name__)

DEMO_WALLET_BALANCE = 5000.00
TRANSACTIONS = [
    {
        "id": "txn_seed_1",
        "type": "wallet",
        "title": "Wallet top-up",
        "amount": 5000.0,
        "status": "completed",
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "meta": {"source": "demo"},
    }
]


def record_demo_transaction(title, kind, amount, status="queued", **meta):
    transaction = {
        "id": f"demo_txn_{len(TRANSACTIONS) + 1}",
        "type": kind,
        "title": title,
        "amount": float(amount),
        "status": status,
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "meta": meta,
    }
    TRANSACTIONS.insert(0, transaction)
    return transaction


def get_user_from_header():
    user_id = request.headers.get("X-User-Id", "").strip()
    if not user_id:
        return None
    return find_user_by_id(user_id)


def get_wallet_balance_for_user(user_id=None):
    if user_id:
        balance = get_wallet_balance(user_id)
        return float(balance) if balance is not None else 0.0
    return float(DEMO_WALLET_BALANCE)


def get_transactions_for_user(user_id=None):
    if user_id:
        return list_transactions(user_id)
    return TRANSACTIONS


def record_transaction_for_user(title, kind, amount, user_id=None, status="queued", **meta):
    if user_id:
        return create_transaction(user_id, title, kind, amount, status, meta)
    return record_demo_transaction(title, kind, amount, status, **meta)


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

    return jsonify({
        "success": True,
        "message": "Login successful",
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "wallet_balance": user["wallet_balance"],
        },
    })


@app.get("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "RAKJID DataHub",
        "provider": "SME API"
    })


@app.get("/api/config")
def config():
    return jsonify({
        "provider": "SME API",
        "demoMode": True,
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
    user = get_user_from_header()
    return jsonify({
        "balance": get_wallet_balance_for_user(user["id"] if user else None),
        "currency": "NGN",
        "status": "active",
    })


@app.post("/api/wallet/topup")
def wallet_topup():
    user = get_user_from_header()
    user_id = user["id"] if user is not None else None

    payload = request.get_json(silent=True) or {}
    amount = float(payload.get("amount", 0) or 0)

    if amount <= 0:
        return jsonify({
            "success": False,
            "message": "amount must be greater than zero"
        }), 400

    if user is not None:
        balance = change_wallet_balance(user_id, amount)
    else:
        global DEMO_WALLET_BALANCE
        DEMO_WALLET_BALANCE += amount
        balance = DEMO_WALLET_BALANCE

    transaction = record_transaction_for_user(
        "Wallet top-up",
        "wallet",
        amount,
        user_id=user_id,
        status="completed",
        source="demo_topup",
    )

    return jsonify({
        "success": True,
        "message": "Wallet topped up successfully",
        "data": {
            "balance": balance,
            "amount": amount,
            "transaction_id": transaction["id"],
        },
    })


@app.get("/api/transactions")
def transactions():
    user = get_user_from_header()
    return jsonify({
        "transactions": get_transactions_for_user(user["id"] if user else None),
    })


@app.post("/api/purchase")
def purchase():
    user = get_user_from_header()
    user_id = user["id"] if user is not None else None

    payload = request.get_json(silent=True) or {}
    plan_id = str(payload.get("plan_id", "")).strip()
    phone = str(payload.get("phone", "")).strip()
    network = str(payload.get("network", "")).strip()

    if not plan_id or not phone or not network:
        return jsonify({
            "success": False,
            "message": "plan_id, phone, and network are required"
        }), 400

    plan = next(
        (item for item in get_data_plans() if str(item.get("id", "")) == plan_id),
        None,
    )

    if not plan:
        return jsonify({
            "success": False,
            "message": "Selected plan was not found"
        }), 404

    amount = float(plan.get("amount", 0) or 0)
    if amount <= 0:
        return jsonify({
            "success": False,
            "message": "Invalid plan amount"
        }), 400

    current_balance = get_wallet_balance_for_user(user_id)
    if current_balance < amount:
        return jsonify({
            "success": False,
            "message": "Insufficient wallet balance"
        }), 402

    if user is not None:
        change_wallet_balance(user_id, -amount)
    else:
        global DEMO_WALLET_BALANCE
        DEMO_WALLET_BALANCE -= amount

    transaction = record_transaction_for_user(
        f"{network} data purchase",
        "data",
        amount,
        user_id=user_id,
        status="queued",
        phone=phone,
        plan_id=plan_id,
        network=network,
    )

    return jsonify({
        "success": True,
        "message": "Purchase queued successfully",
        "data": {
            "plan_id": plan_id,
            "network": network,
            "phone": phone,
            "plan_name": plan.get("plan") or plan.get("name") or "Data plan",
            "amount": amount,
            "status": "queued",
            "transaction_id": transaction["id"],
        }
    })


@app.post("/api/airtime")
def airtime_purchase():
    user = get_user_from_header()
    user_id = user["id"] if user is not None else None

    payload = request.get_json(silent=True) or {}
    phone = str(payload.get("phone", "")).strip()
    network = str(payload.get("network", "")).strip()
    amount = float(payload.get("amount", 0) or 0)

    if not phone or not network or amount <= 0:
        return jsonify({
            "success": False,
            "message": "phone, network, and amount are required"
        }), 400

    current_balance = get_wallet_balance_for_user(user_id)
    if current_balance < amount:
        return jsonify({
            "success": False,
            "message": "Insufficient wallet balance"
        }), 402

    if user is not None:
        change_wallet_balance(user_id, -amount)
    else:
        global DEMO_WALLET_BALANCE
        DEMO_WALLET_BALANCE -= amount

    transaction = record_transaction_for_user(
        f"{network} airtime purchase",
        "airtime",
        amount,
        user_id=user_id,
        status="queued",
        phone=phone,
        network=network,
    )

    return jsonify({
        "success": True,
        "message": "Airtime purchase queued successfully",
        "data": {
            "phone": phone,
            "network": network,
            "amount": amount,
            "status": "queued",
            "transaction_id": transaction["id"],
        },
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

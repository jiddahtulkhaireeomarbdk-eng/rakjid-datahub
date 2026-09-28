import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timezone


DEFAULT_BALANCE = 0.0
DATABASE_PATH = os.getenv(
    "DATAHUB_DATABASE_PATH",
    os.path.join(os.path.dirname(__file__), "datahub.sqlite3"),
)


def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    connection = get_connection()
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                wallet_balance REAL NOT NULL DEFAULT 0.0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                amount REAL NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                meta TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_transactions_user_created
            ON transactions(user_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_password_reset_user
            ON password_reset_tokens(user_id);

            CREATE TABLE IF NOT EXISTS wallet_fundings (
                reference TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                amount_kobo INTEGER NOT NULL CHECK (amount_kobo > 0),
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_wallet_fundings_user
            ON wallet_fundings(user_id, created_at DESC);
            """
        )
        connection.commit()
    finally:
        connection.close()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120000,
    ).hex()
    return f"{salt}${digest}"


def _verify_password(password, stored_hash):
    try:
        salt, expected_digest = stored_hash.split("$", 1)
    except ValueError:
        return False

    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120000,
    ).hex()
    return secrets.compare_digest(actual_digest, expected_digest)


def _user_payload(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "wallet_balance": float(row["wallet_balance"]),
    }


def create_user(name, email, password):
    user_id = f"user_{secrets.token_urlsafe(12)}"
    connection = get_connection()
    try:
        connection.execute(
            """
            INSERT INTO users (id, name, email, password_hash, wallet_balance, created_at)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (user_id, name, email, _hash_password(password), _now()),
        )
        connection.commit()
        row = connection.execute(
            "SELECT id, name, email, wallet_balance FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return _user_payload(row)
    finally:
        connection.close()


def find_user_by_email(email):
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT * FROM users WHERE email = ? COLLATE NOCASE",
            (email,),
        ).fetchone()
        return row
    finally:
        connection.close()


def find_user_by_id(user_id):
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT id, name, email, wallet_balance FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return _user_payload(row) if row else None
    finally:
        connection.close()


def authenticate_user(email, password):
    row = find_user_by_email(email)
    if row is None or not _verify_password(password, row["password_hash"]):
        return None
    return _user_payload(row)


def store_password_reset_token(user_id, token_hash, expires_at):
    connection = get_connection()
    try:
        connection.execute(
            "DELETE FROM password_reset_tokens WHERE user_id = ?",
            (user_id,),
        )
        connection.execute(
            """
            INSERT INTO password_reset_tokens (token_hash, user_id, expires_at)
            VALUES (?, ?, ?)
            """,
            (token_hash, user_id, int(expires_at)),
        )
        connection.commit()
    finally:
        connection.close()


def reset_password_with_token(token_hash, password, current_time):
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        token = connection.execute(
            """
            SELECT user_id FROM password_reset_tokens
            WHERE token_hash = ? AND expires_at > ?
            """,
            (token_hash, int(current_time)),
        ).fetchone()
        if token is None:
            connection.rollback()
            return False

        connection.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (_hash_password(password), token["user_id"]),
        )
        connection.execute(
            "DELETE FROM password_reset_tokens WHERE user_id = ?",
            (token["user_id"],),
        )
        connection.commit()
        return True
    finally:
        connection.close()


def get_wallet_balance(user_id):
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT wallet_balance FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return float(row["wallet_balance"]) if row else None
    finally:
        connection.close()


def change_wallet_balance(user_id, amount):
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ?",
            (float(amount), user_id),
        )
        row = connection.execute(
            "SELECT wallet_balance FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        connection.commit()
        return float(row["wallet_balance"]) if row else None
    finally:
        connection.close()


def create_wallet_funding(reference, user_id, amount_kobo):
    connection = get_connection()
    try:
        connection.execute(
            """
            INSERT INTO wallet_fundings (reference, user_id, amount_kobo, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (reference, user_id, int(amount_kobo), _now()),
        )
        connection.commit()
    finally:
        connection.close()


def get_wallet_funding(reference, user_id=None):
    connection = get_connection()
    try:
        if user_id is None:
            row = connection.execute(
                "SELECT * FROM wallet_fundings WHERE reference = ?",
                (reference,),
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT * FROM wallet_fundings WHERE reference = ? AND user_id = ?",
                (reference, user_id),
            ).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def complete_wallet_funding(reference, amount_kobo):
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        funding = connection.execute(
            "SELECT * FROM wallet_fundings WHERE reference = ?",
            (reference,),
        ).fetchone()
        if funding is None or funding["amount_kobo"] != int(amount_kobo):
            connection.rollback()
            return None

        if funding["status"] == "completed":
            row = connection.execute(
                "SELECT wallet_balance FROM users WHERE id = ?",
                (funding["user_id"],),
            ).fetchone()
            connection.commit()
            return {"balance": float(row["wallet_balance"]), "credited": False}

        amount = int(amount_kobo) / 100
        connection.execute(
            "UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ?",
            (amount, funding["user_id"]),
        )
        transaction_id = f"txn_{secrets.token_urlsafe(12)}"
        connection.execute(
            """
            INSERT INTO transactions
                (id, user_id, type, title, amount, status, created_at, meta)
            VALUES (?, ?, 'wallet', 'Paystack wallet funding', ?, 'completed', ?, ?)
            """,
            (
                transaction_id,
                funding["user_id"],
                amount,
                _now(),
                __import__("json").dumps({"provider": "paystack", "reference": reference}),
            ),
        )
        connection.execute(
            "UPDATE wallet_fundings SET status = 'completed', completed_at = ? WHERE reference = ?",
            (_now(), reference),
        )
        row = connection.execute(
            "SELECT wallet_balance FROM users WHERE id = ?",
            (funding["user_id"],),
        ).fetchone()
        connection.commit()
        return {"balance": float(row["wallet_balance"]), "credited": True}
    finally:
        connection.close()


def create_transaction(user_id, title, kind, amount, status="queued", meta=None):
    transaction_id = f"txn_{secrets.token_urlsafe(12)}"
    connection = get_connection()
    try:
        connection.execute(
            """
            INSERT INTO transactions
                (id, user_id, type, title, amount, status, created_at, meta)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transaction_id,
                user_id,
                kind,
                title,
                float(amount),
                status,
                _now(),
                __import__("json").dumps(meta or {}),
            ),
        )
        connection.commit()
        row = connection.execute(
            "SELECT id, type, title, amount, status, created_at, meta FROM transactions WHERE id = ?",
            (transaction_id,),
        ).fetchone()
        return transaction_to_dict(row)
    finally:
        connection.close()


def reserve_wallet_purchase(user_id, title, kind, amount, meta=None):
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            """
            UPDATE users SET wallet_balance = wallet_balance - ?
            WHERE id = ? AND wallet_balance >= ?
            """,
            (float(amount), user_id, float(amount)),
        )
        if cursor.rowcount != 1:
            connection.rollback()
            return None

        transaction_id = f"txn_{secrets.token_urlsafe(12)}"
        connection.execute(
            """
            INSERT INTO transactions
                (id, user_id, type, title, amount, status, created_at, meta)
            VALUES (?, ?, ?, ?, ?, 'processing', ?, ?)
            """,
            (
                transaction_id,
                user_id,
                kind,
                title,
                float(amount),
                _now(),
                __import__("json").dumps(meta or {}),
            ),
        )
        row = connection.execute(
            """
            SELECT id, type, title, amount, status, created_at, meta
            FROM transactions WHERE id = ?
            """,
            (transaction_id,),
        ).fetchone()
        connection.commit()
        return transaction_to_dict(row)
    finally:
        connection.close()


def settle_wallet_purchase(transaction_id, user_id, status, refund=False):
    if status not in ("completed", "failed"):
        raise ValueError("Purchase settlement status must be completed or failed")

    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        transaction = connection.execute(
            """
            SELECT amount FROM transactions
            WHERE id = ? AND user_id = ? AND type IN ('data', 'airtime')
              AND status = 'processing'
            """,
            (transaction_id, user_id),
        ).fetchone()
        if transaction is None:
            connection.rollback()
            return False

        if refund:
            connection.execute(
                "UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ?",
                (transaction["amount"], user_id),
            )
        connection.execute(
            "UPDATE transactions SET status = ? WHERE id = ?",
            (status, transaction_id),
        )
        connection.commit()
        return True
    finally:
        connection.close()


def transaction_to_dict(row):
    import json

    return {
        "id": row["id"],
        "type": row["type"],
        "title": row["title"],
        "amount": float(row["amount"]),
        "status": row["status"],
        "created_at": row["created_at"],
        "meta": json.loads(row["meta"] or "{}"),
    }


def list_transactions(user_id):
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT id, type, title, amount, status, created_at, meta
            FROM transactions
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
        return [transaction_to_dict(row) for row in rows]
    finally:
        connection.close()


init_db()

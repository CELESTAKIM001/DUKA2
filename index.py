"""
M-Pesa E-Commerce Store — Vercel Serverless + MongoDB Atlas + Daraja STK Push
api/index.py  (single entry-point, routed by vercel.json)
"""

import os
import base64
import datetime
import requests
from bson import ObjectId
from flask import Flask, render_template, request, jsonify, redirect, url_for
from pymongo import MongoClient, DESCENDING

# ─────────────────────────────────────────────────────────────────────────────
# App bootstrap
# ─────────────────────────────────────────────────────────────────────────────
app = Flask(
    __name__,
    template_folder="../templates",
    static_folder="../static",
)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-me-in-prod")

# ─────────────────────────────────────────────────────────────────────────────
# 1. Serverless-safe MongoDB connection pool (single global client)
# ─────────────────────────────────────────────────────────────────────────────
_mongo_client: MongoClient | None = None


def get_db():
    """Return a reused MongoClient database handle (connection-pool safe)."""
    global _mongo_client
    if _mongo_client is None:
        uri = os.environ.get("MONGODB_URI", "")
        if not uri:
            raise RuntimeError("MONGODB_URI environment variable is not set.")
        _mongo_client = MongoClient(
            uri,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            maxPoolSize=10,          # serverless: keep pool small
            retryWrites=True,
        )
    return _mongo_client[os.environ.get("MONGODB_DB", "mpesa_store")]


# ─────────────────────────────────────────────────────────────────────────────
# 2. Safe environment-variable helpers
# ─────────────────────────────────────────────────────────────────────────────
def _env(key: str, fallback: str = "") -> str:
    """Never raises KeyError; returns empty string if variable is absent."""
    return os.environ.get(key) or fallback


MPESA_BASE_URL        = _env("MPESA_BASE_URL",        "https://sandbox.safaricom.co.ke")
MPESA_CONSUMER_KEY    = _env("MPESA_CONSUMER_KEY")
MPESA_CONSUMER_SECRET = _env("MPESA_CONSUMER_SECRET")
MPESA_SHORTCODE       = _env("MPESA_SHORTCODE",       "174379")        # sandbox default
MPESA_PASSKEY         = _env("MPESA_PASSKEY")
MPESA_CALLBACK_URL    = _env("MPESA_CALLBACK_URL",    "https://your-domain.vercel.app/api/mpesa/callback")


# ─────────────────────────────────────────────────────────────────────────────
# Daraja helpers
# ─────────────────────────────────────────────────────────────────────────────
def _daraja_token() -> str:
    """Fetch a short-lived OAuth token from Safaricom."""
    creds = base64.b64encode(
        f"{MPESA_CONSUMER_KEY}:{MPESA_CONSUMER_SECRET}".encode()
    ).decode()
    r = requests.get(
        f"{MPESA_BASE_URL}/oauth/v1/generate?grant_type=client_credentials",
        headers={"Authorization": f"Basic {creds}"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _stk_password_and_timestamp():
    """Return (base64_password, timestamp_str) for STK Push."""
    ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    raw = f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{ts}"
    pwd = base64.b64encode(raw.encode()).decode()
    return pwd, ts


# ─────────────────────────────────────────────────────────────────────────────
# 3. BSON → JSON-safe serialisation helper
# ─────────────────────────────────────────────────────────────────────────────
def _serialize(doc: dict) -> dict:
    """Convert ObjectId fields to strings so they are JSON/template safe."""
    out = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            out[k] = str(v)
        elif isinstance(v, datetime.datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


# ─────────────────────────────────────────────────────────────────────────────
# ROUTES — Storefront
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/")
def storefront():
    try:
        db = get_db()
        raw_products = list(db.products.find().sort("_id", DESCENDING))
        products = [_serialize(p) for p in raw_products]
    except Exception as exc:
        app.logger.error("DB error on storefront: %s", exc)
        products = []
    return render_template("store.html", products=products)


# ─────────────────────────────────────────────────────────────────────────────
# ROUTES — Admin
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/admin", methods=["GET"])
def admin():
    try:
        db = get_db()
        raw_orders = list(db.orders.find().sort("created_at", DESCENDING).limit(200))
        orders = [_serialize(o) for o in raw_orders]
    except Exception as exc:
        app.logger.error("DB error on admin: %s", exc)
        orders = []
    return render_template("admin.html", orders=orders)


@app.route("/admin/product", methods=["POST"])
def admin_add_product():
    """Publish a new product to the catalogue."""
    try:
        db = get_db()
        # 3. Strict type-conversion inside try/except
        price_before = float(request.form.get("priceBefore", 0) or 0)
        price_after  = float(request.form.get("priceAfter",  0) or 0)
        doc = {
            "title":       request.form.get("title", "").strip(),
            "description": request.form.get("description", "").strip(),
            "imageUrl":    request.form.get("imageUrl", "").strip(),
            "priceBefore": price_before,
            "priceAfter":  price_after,
            "created_at":  datetime.datetime.utcnow(),
        }
        if not doc["title"]:
            return redirect(url_for("admin") + "?error=Title+is+required")
        db.products.insert_one(doc)
    except ValueError as exc:
        app.logger.error("Price conversion error: %s", exc)
        return redirect(url_for("admin") + "?error=Invalid+price+format")
    except Exception as exc:
        app.logger.error("Admin product insert error: %s", exc)
        return redirect(url_for("admin") + "?error=Database+error")
    return redirect(url_for("admin") + "?success=Product+added")


# ─────────────────────────────────────────────────────────────────────────────
# ROUTES — Checkout API
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/api/checkout", methods=["POST"])
def checkout():
    """Initiate STK Push and create a pending order record."""
    payload = request.get_json(force=True, silent=True) or {}

    # 3. Safe type conversion
    try:
        amount      = int(float(str(payload.get("amount", 1))))
        phone       = str(payload.get("phone", "")).strip().replace("+", "")
        product_id  = str(payload.get("product_id", "")).strip()
        description = str(payload.get("description", "Order"))[:50]
    except (ValueError, TypeError) as exc:
        return jsonify({"error": f"Invalid input: {exc}"}), 400

    if not phone or not product_id:
        return jsonify({"error": "Phone and product_id are required."}), 400

    # Normalise phone to 2547XXXXXXXX format
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    if not phone.startswith("254") or len(phone) != 12:
        return jsonify({"error": "Invalid Kenyan phone number. Use 07XXXXXXXX."}), 400

    # Create pending order first so we have a checkout_id
    try:
        db = get_db()
        order_doc = {
            "product_id":  product_id,
            "phone":       phone,
            "amount":      amount,
            "description": description,
            "status":      "Pending",
            "mpesa_receipt": None,
            "checkout_request_id": None,
            "created_at":  datetime.datetime.utcnow(),
        }
        result     = db.orders.insert_one(order_doc)
        order_id   = str(result.inserted_id)
    except Exception as exc:
        app.logger.error("Order insert error: %s", exc)
        return jsonify({"error": "Database error, please retry."}), 500

    # Trigger STK Push
    try:
        token = _daraja_token()
        password, timestamp = _stk_password_and_timestamp()
        stk_payload = {
            "BusinessShortCode": MPESA_SHORTCODE,
            "Password":          password,
            "Timestamp":         timestamp,
            "TransactionType":   "CustomerBuyGoodsOnline",
            "Amount":            amount,
            "PartyA":            phone,
            "PartyB":            MPESA_SHORTCODE,
            "PhoneNumber":       phone,
            "CallBackURL":       MPESA_CALLBACK_URL,
            "AccountReference":  order_id,
            "TransactionDesc":   description,
        }
        resp = requests.post(
            f"{MPESA_BASE_URL}/mpesa/stkpush/v1/processrequest",
            json=stk_payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        stk_data = resp.json()

        # Persist the CheckoutRequestID for later status queries
        checkout_request_id = stk_data.get("CheckoutRequestID", "")
        db.orders.update_one(
            {"_id": result.inserted_id},
            {"$set": {"checkout_request_id": checkout_request_id}},
        )
        return jsonify({
            "success":     True,
            "checkout_id": order_id,
            "message":     "STK Push sent. Check your phone.",
        })
    except requests.exceptions.HTTPError as exc:
        db.orders.update_one({"_id": result.inserted_id}, {"$set": {"status": "Failed"}})
        app.logger.error("Daraja STK error: %s – %s", exc, exc.response.text if exc.response else "")
        return jsonify({"error": "M-Pesa request failed. Check credentials or try again."}), 502
    except Exception as exc:
        db.orders.update_one({"_id": result.inserted_id}, {"$set": {"status": "Failed"}})
        app.logger.error("STK Push unexpected error: %s", exc)
        return jsonify({"error": "Unexpected error during payment initiation."}), 500


# ─────────────────────────────────────────────────────────────────────────────
# ROUTES — Status polling
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/api/checkout/status/<checkout_id>")
def checkout_status(checkout_id: str):
    """5. Clean long-poll status endpoint for the frontend interval."""
    try:
        db    = get_db()
        order = db.orders.find_one({"_id": ObjectId(checkout_id)})
        if not order:
            return jsonify({"error": "Order not found."}), 404
        return jsonify({
            "status":        order.get("status", "Pending"),
            "mpesa_receipt": order.get("mpesa_receipt"),
            "amount":        order.get("amount"),
        })
    except Exception as exc:
        app.logger.error("Status check error: %s", exc)
        return jsonify({"error": "Could not retrieve order status."}), 500


# ─────────────────────────────────────────────────────────────────────────────
# 4. M-Pesa Callback Webhook
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/api/mpesa/callback", methods=["POST"])
def mpesa_callback():
    """
    Safaricom posts the payment result here.
    Always return HTTP 200 with ResultCode=0 so Safaricom doesn't retry.
    """
    # 4. Use force=True to parse regardless of Content-Type header
    try:
        data     = request.get_json(force=True, silent=True) or {}
        callback = data.get("Body", {}).get("stkCallback", {})
        result_code    = callback.get("ResultCode")
        checkout_req   = callback.get("CheckoutRequestID", "")
        metadata_items = callback.get("CallbackMetadata", {}).get("Item", [])

        # Extract receipt and amount from metadata list
        receipt = None
        amount  = None
        for item in metadata_items:
            if item.get("Name") == "MpesaReceiptNumber":
                receipt = item.get("Value")
            if item.get("Name") == "Amount":
                try:
                    amount = float(item.get("Value", 0))
                except (ValueError, TypeError):
                    amount = None

        db = get_db()
        if result_code == 0:
            # Payment successful
            db.orders.update_one(
                {"checkout_request_id": checkout_req},
                {"$set": {
                    "status":        "Paid",
                    "mpesa_receipt": receipt,
                    "paid_amount":   amount,
                    "paid_at":       datetime.datetime.utcnow(),
                }},
            )
        else:
            # Payment cancelled or failed
            db.orders.update_one(
                {"checkout_request_id": checkout_req},
                {"$set": {
                    "status":     "Failed",
                    "result_code": result_code,
                }},
            )
    except Exception as exc:
        # Silent internal error — never expose to Safaricom
        app.logger.error("Callback processing error: %s", exc)

    # 4. Always acknowledge with HTTP 200 to prevent Safaricom retry loops
    return jsonify({"ResultCode": 0, "ResultDescription": "Success"}), 200


# ─────────────────────────────────────────────────────────────────────────────
# Vercel WSGI entry-point
# ─────────────────────────────────────────────────────────────────────────────
# Vercel looks for a variable named `app` (or a handler) in api/index.py
# Flask's WSGI callable is already named `app` — nothing extra needed.

if __name__ == "__main__":
    app.run(debug=True, port=5000)

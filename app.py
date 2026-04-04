from flask import Flask, request, jsonify
import os
import requests
import hashlib
import hmac
import json
from datetime import datetime

app = Flask(__name__)

# Base44 API endpoint
BASE44_API_URL = os.getenv("https://christravel.base44.app/api/functions/updateUserSubscription")
if not BASE44_API_URL:
    raise ValueError("BASE44_API_URL environment variable not set!")

# Paystack secret key
PAYSTACK_SECRET = os.getenv("sk_test_53bfe4e8394232ff2e9647ea5404b9ed9c9da729")
if not PAYSTACK_SECRET:
    raise ValueError("PAYSTACK_SECRET environment variable not set!")

# -----------------------------
# Verify Paystack signature
# -----------------------------
def verify_signature(payload, signature):
    computed = hmac.new(
        PAYSTACK_SECRET.encode('utf-8'),
        payload,
        hashlib.sha512
    ).hexdigest()
    return computed == signature

# -----------------------------
# Webhook route
# -----------------------------
@app.route('/webhook', methods=['POST'])
def webhook():
    signature = request.headers.get('x-paystack-signature')
    if not signature:
        return jsonify({"error": "Missing signature header"}), 400

    if not verify_signature(request.data, signature):
        return jsonify({"error": "Invalid signature"}), 400

    # Parse payload
    try:
        data = request.json
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    event = data.get("event")
    customer = data.get("data", {}).get("customer", {})
    email = customer.get("email")

    if not event or not email:
        return jsonify({"error": "Missing required data"}), 400

    # -----------------------------
    # Determine subscription status
    # -----------------------------
    # Default: ignore unrelated events
    status = None

    if event in ["charge.success", "subscription.create", "subscription.activate"]:
        status = "active"
    elif event in ["subscription.disable", "invoice.payment_failed", "charge.failed"]:
        status = "inactive"
    elif event == "subscription.cancel":
        # User cancelled manually
        status = "inactive"
    else:
        # Ignore unrelated events
        return jsonify({"message": f"Ignored event: {event}"}), 200

    # -----------------------------
    # Prepare Base44 payload
    # -----------------------------
    payload = {
        "email": email,
        "subscription_status": status,
        "last_payment_date": datetime.utcnow().isoformat() + "Z" if status == "active" else None
    }

    # -----------------------------
    # Send update to Base44
    # -----------------------------
    try:
        res = requests.post(BASE44_API_URL, json=payload, timeout=10)
        res.raise_for_status()
    except requests.RequestException as e:
        # Log error and return 500 for Paystack retry
        print("Error sending to Base44:", e)
        return jsonify({"error": "Failed to update Base44"}), 500

    print(f"Webhook processed: {event} for {email} -> {status}")
    return jsonify({"message": "OK"}), 200

# -----------------------------
# Run server
# -----------------------------
if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

from flask import Flask, request, jsonify
import requests
import hashlib
import hmac
import os
from datetime import datetime, timedelta

app = Flask(__name__)

BASE44_API_URL = os.getenv("BASE44_API_URL")
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET")

# --- Helper: Verify Paystack signature ---
def verify_signature(request_data, signature):
    computed_hash = hmac.new(
        PAYSTACK_SECRET.encode('utf-8'),
        request_data,
        hashlib.sha512
    ).hexdigest()
    return computed_hash == signature


# --- Helper: Calculate next billing date ---
def calculate_next_payment(paid_at):
    dt = datetime.fromisoformat(paid_at.replace("Z", ""))
    return (dt + timedelta(days=30)).isoformat()


@app.route('/webhook', methods=['POST'])
def webhook():
    signature = request.headers.get('x-paystack-signature')

    # 🔒 SECURITY: Verify signature
    if not signature or not verify_signature(request.data, signature):
        return jsonify({"error": "Invalid signature"}), 400

    data = request.json
    event = data.get("event")
    payment_data = data.get("data", {})

    # 🔍 Extract important fields
    event_id = payment_data.get("id")
    email = payment_data.get("customer", {}).get("email")

    if not event or not email:
        return jsonify({"error": "Missing event or email"}), 400

    print(f"Event: {event} | Email: {email} | ID: {event_id}")

    # --- HANDLE SUCCESSFUL PAYMENT ONLY ---
    if event == "charge.success":

        if payment_data.get("status") != "success":
            return jsonify({"message": "Ignored (not successful)"}), 200

        paid_at = payment_data.get("paid_at")

        if not paid_at:
            return jsonify({"error": "Missing paid_at"}), 400

        next_payment_date = calculate_next_payment(paid_at)

        payload = {
            "email": email,
            "subscription_status": "active",
            "last_payment_date": paid_at,
            "next_payment_date": next_payment_date,
            "last_event_id": str(event_id)
        }

    # --- HANDLE FAILED PAYMENT ---
    elif event == "invoice.payment_failed":

        # ❗ DO NOT deactivate immediately
        # Let expiry logic handle it
        return jsonify({"message": "Payment failed - waiting for expiry"}), 200

    # --- HANDLE SUBSCRIPTION DISABLE ---
    elif event == "subscription.disable":

        payload = {
            "email": email,
            "subscription_status": "inactive",
            "last_event_id": str(event_id)
        }

    else:
        return jsonify({"message": "Ignored"}), 200

    # --- SEND TO BASE44 ---
    try:
        res = requests.post(BASE44_API_URL, json=payload, timeout=10)
        print("Base44 response:", res.text)
    except Exception as e:
        print("Error sending to Base44:", str(e))
        return jsonify({"error": "Failed to update subscription"}), 500

    return jsonify({"message": "OK"}), 200


if __name__ == '__main__':
    app.run(port=5000)

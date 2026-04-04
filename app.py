from flask import Flask, request, jsonify
import requests
import hashlib
import hmac
import os
from datetime import datetime, timedelta

app = Flask(__name__)

BASE44_API_URL = os.getenv("BASE44_API_URL")
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET")


# 🔒 Verify Paystack signature
def verify_signature(request_data, signature):
    computed_hash = hmac.new(
        PAYSTACK_SECRET.encode('utf-8'),
        request_data,
        hashlib.sha512
    ).hexdigest()
    return computed_hash == signature


# 📅 Calculate next billing date (monthly)
def calculate_next_payment(paid_at):
    dt = datetime.fromisoformat(paid_at.replace("Z", ""))
    return (dt + timedelta(days=30)).isoformat()


@app.route('/webhook', methods=['POST'])
def webhook():
    signature = request.headers.get('x-paystack-signature')

    # 🔐 SECURITY CHECK
    if not signature or not verify_signature(request.data, signature):
        return jsonify({"error": "Invalid signature"}), 400

    data = request.json
    event = data.get("event")
    payload_data = data.get("data", {})

    event_id = str(payload_data.get("id"))

    print(f"Incoming event: {event} | ID: {event_id}")

    # -------------------------
    # 🔁 HANDLE EVENTS
    # -------------------------

    # ✅ 1. SUCCESSFUL PAYMENT
    if event == "charge.success":

        if payload_data.get("status") != "success":
            return jsonify({"message": "Ignored"}), 200

        email = payload_data.get("customer", {}).get("email")
        paid_at = payload_data.get("paid_at")

        if not email or not paid_at:
            return jsonify({"error": "Missing email or paid_at"}), 400

        plan_code = payload_data.get("plan", {}).get("plan_code")

        # ⚠️ subscription_code may be missing here
        subscription_code = payload_data.get("subscription", {}).get("subscription_code")

        next_payment_date = calculate_next_payment(paid_at)

        update_payload = {
            "email": email,
            "subscription_status": "active",
            "plan_code": plan_code,
            "subscription_code": subscription_code,
            "last_payment_date": paid_at,
            "next_payment_date": next_payment_date,
            "last_event_id": event_id
        }

    # ✅ 2. SUBSCRIPTION CREATED (IMPORTANT for subscription_code)
    elif event == "subscription.create":

        email = payload_data.get("customer", {}).get("email")

        if not email:
            return jsonify({"error": "Missing email"}), 400

        update_payload = {
            "email": email,
            "subscription_code": payload_data.get("subscription_code"),
            "plan_code": payload_data.get("plan", {}).get("plan_code"),
            "last_event_id": event_id
        }

    # ❌ 3. PAYMENT FAILED (do nothing — expiry handles it)
    elif event == "invoice.payment_failed":
        return jsonify({"message": "Payment failed - waiting for expiry"}), 200

    # ❌ 4. SUBSCRIPTION DISABLED
    elif event == "subscription.disable":

        email = payload_data.get("customer", {}).get("email")

        if not email:
            return jsonify({"error": "Missing email"}), 400

        update_payload = {
            "email": email,
            "subscription_status": "inactive",
            "last_event_id": event_id
        }

    else:
        return jsonify({"message": "Ignored"}), 200

    # -------------------------
    # 📡 SEND TO BASE44
    # -------------------------
    try:
        res = requests.post(BASE44_API_URL, json=update_payload, timeout=10)
        print("Base44 response:", res.text)
    except Exception as e:
        print("Error sending to Base44:", str(e))
        return jsonify({"error": "Failed to update Base44"}), 500

    return jsonify({"message": "OK"}), 200


if __name__ == '__main__':
    app.run(port=5000)

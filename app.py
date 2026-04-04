from flask import Flask, request, jsonify
import requests
import hashlib
import hmac
import os
from datetime import datetime, timedelta

app = Flask(__name__)

BASE44_API_URL = os.getenv("https://christravel.base44.app/api/functions/updateUserSubscription")
PAYSTACK_SECRET = os.getenv("sk_test_53bfe4e8394232ff2e9647ea5404b9ed9c9da729")


# 🔒 Verify Paystack signature
def verify_signature(request_data, signature):
    computed_hash = hmac.new(
        PAYSTACK_SECRET.encode('utf-8'),
        request_data,
        hashlib.sha512
    ).hexdigest()
    return computed_hash == signature


# 📅 Calculate next billing date
def calculate_next_payment(paid_at):
    dt = datetime.fromisoformat(paid_at.replace("Z", ""))
    return (dt + timedelta(days=30)).isoformat()


@app.route('/webhook', methods=['POST'])
def webhook():
    signature = request.headers.get('x-paystack-signature')

    # 🔐 SECURITY
    if not signature or not verify_signature(request.data, signature):
        return jsonify({"error": "Invalid signature"}), 400

    data = request.json
    event = data.get("event")
    payload_data = data.get("data", {})

    event_id = str(payload_data.get("id"))
    email = payload_data.get("customer", {}).get("email")

    print(f"Event: {event} | Email: {email} | ID: {event_id}")

    if not email:
        return jsonify({"error": "Missing email"}), 400

    update_payload = {
        "email": email,
        "last_event_id": event_id
    }

    # -------------------------
    # ✅ SUCCESSFUL PAYMENT
    # -------------------------
    if event == "charge.success":

        if payload_data.get("status") != "success":
            return jsonify({"message": "Ignored"}), 200

        paid_at = payload_data.get("paid_at")
        plan_code = payload_data.get("plan", {}).get("plan_code")

        next_payment_date = calculate_next_payment(paid_at)

        update_payload.update({
            "subscription_status": "active",
            "plan_code": plan_code,
            "last_payment_date": paid_at,
            "next_payment_date": next_payment_date,
            "cancel_at_period_end": False  # 🔥 reset cancel if user pays again
        })

    # -------------------------
    # ✅ SUBSCRIPTION CREATED
    # -------------------------
    elif event == "subscription.create":

        update_payload.update({
            "subscription_code": payload_data.get("subscription_code"),
            "plan_code": payload_data.get("plan", {}).get("plan_code"),
            "email_token": payload_data.get("email_token"),
            "cancel_at_period_end": False
        })

    # -------------------------
    # ❌ PAYMENT FAILED
    # -------------------------
    elif event == "invoice.payment_failed":
        return jsonify({"message": "Ignored (handled by expiry)"}), 200

    # -------------------------
    # ❌ SUBSCRIPTION CANCELLED
    # -------------------------
    elif event == "subscription.disable":

        update_payload.update({
            "cancel_at_period_end": True
        })

    else:
        return jsonify({"message": "Ignored"}), 200

    # -------------------------
    # 📡 SEND TO BASE44
    # -------------------------
    try:
        res = requests.post(BASE44_API_URL, json=update_payload, timeout=10)
        print("Base44 response:", res.text)
    except Exception as e:
        print("Error:", str(e))
        return jsonify({"error": "Failed to update Base44"}), 500

    return jsonify({"message": "OK"}), 200


if __name__ == '__main__':
    app.run(port=5000)

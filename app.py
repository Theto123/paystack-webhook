from flask import Flask, request, jsonify
import requests
import hashlib
import hmac

app = Flask(__name__)

BASE44_API_URL = "https://christravel.base44.app/api/functions/updateUserSubscription"
PAYSTACK_SECRET = "YOUR_SECRET_KEY"

@app.route('/webhook', methods=['POST'])
def webhook():
    # Verify signature
    signature = request.headers.get('x-paystack-signature')
    computed_hash = hmac.new(
        PAYSTACK_SECRET.encode('utf-8'),
        request.data,
        hashlib.sha512
    ).hexdigest()

    if computed_hash != signature:
        return jsonify({"error": "Invalid signature"}), 400

    data = request.json
    print("Incoming:", data)

    event = data.get("event")
    customer = data.get("data", {}).get("customer", {})
    email = customer.get("email")

    if not event or not email:
        return jsonify({"error": "Missing data"}), 400

    # Handle events
    if event in ["charge.success", "subscription.create"]:
        status = "active"
    elif event in ["invoice.payment_failed", "subscription.disable"]:
        status = "inactive"
    else:
        return jsonify({"message": "Ignored"}), 200

    payload = {
        "email": email,
        "subscription_status": status
    }

    try:
        res = requests.post(BASE44_API_URL, json=payload)
        print("Base44 response:", res.text)
    except Exception as e:
        print("Error:", e)

    return jsonify({"message": "OK"}), 200


if __name__ == '__main__':
    app.run(port=5000)
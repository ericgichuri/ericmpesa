import os
from flask import Flask, request, jsonify
import redis
import json

app = Flask(__name__)

def get_redis_client():
    """Fetches the exact environment variable recommended by the Vercel Python tab."""
    # Read the direct variable Vercel showed you
    redis_url = os.environ.get('REDIS_URL')
    
    if not redis_url:
        return None
        
    # Connect simply without manual string replacements or custom SSL parameters
    return redis.Redis.from_url(redis_url, decode_responses=True, socket_timeout=3)


@app.route('/mpesa/stk-callback', methods=['POST'])
def stk_callback():
    kv = get_redis_client()
    if kv is None:
        return jsonify({"ResultCode": 1, "ResultDesc": "Redis configuration missing on Vercel"}), 500

    data = request.get_json()
    stk_callback_data = data.get("Body", {}).get("stkCallback", {})
    
    if stk_callback_data.get("ResultCode") == 0:
        metadata = stk_callback_data.get("CallbackMetadata", {}).get("Item", [])
        
        extracted = {}
        for item in metadata:
            extracted[item["Name"]] = item.get("Value")
            
        # Defensive extraction logic to ensure data remains consistent for SQLite types
        try:
            amount_val = float(extracted.get("Amount", 0))
        except (ValueError, TypeError):
            amount_val = 0.0

        log_entry = {
            "mpesa_trx_id": extracted.get("MpesaReceiptNumber"),
            "amount": amount_val,
            "phone_number": str(extracted.get("PhoneNumber")),
            "customer_name": "STK Push Payment",
            "account_ref": str(stk_callback_data.get("MerchantRequestID")),
            "created_at": request.headers.get('X-Vercel-Id', 'Just Now')
        }
        
        kv.rpush("mpesa_pool", json.dumps(log_entry))
            
    return jsonify({"ResultCode": 0, "ResultDesc": "Success"})


@app.route('/fetch-bridge-logs', methods=['GET'])
def fetch_bridge_logs():
    kv = get_redis_client()
    
    if kv is None:
        return jsonify({
            "status": "error",
            "message": "The Redis client 'kv' could not be initialized dynamically. Check if KV_URL environment variable is set in Vercel settings.",
            "logs": []
        }), 200

    try:
        raw_logs = kv.lrange("mpesa_pool", 0, -1) or []
        parsed_logs = [json.loads(log) for log in raw_logs]
        
        if raw_logs:
            kv.delete("mpesa_pool")
            
        return jsonify({"status": "success", "logs": parsed_logs})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Redis Runtime Error: {str(e)}", "logs": []}), 200

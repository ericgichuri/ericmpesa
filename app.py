import os
from flask import Flask, request, jsonify
import redis
import json

app = Flask(__name__)

KV_URL = (
    os.environ.get("KV_URL") or 
    os.environ.get("KV_URL_NON_POOLING") or 
    os.environ.get("REDIS_URL")
)

kv = None
if KV_URL:
    # Upgrade standard redis:// schema to rediss:// for secure cloud TLS Handshakes
    if KV_URL.startswith("redis://"):
        KV_URL = KV_URL.replace("redis://", "rediss://", 1)
    
    # We add a connection_timeout of 3 seconds to keep execution fast
    kv = redis.Redis.from_url(KV_URL, decode_responses=True, socket_timeout=3)

@app.route('/mpesa/stk-callback', methods=['POST'])
def stk_callback():
    data = request.get_json()
    stk_callback_data = data.get("Body", {}).get("stkCallback", {})
    
    if stk_callback_data.get("ResultCode") == 0:
        metadata = stk_callback_data.get("CallbackMetadata", {}).get("Item", [])
        
        extracted = {}
        for item in metadata:
            extracted[item["Name"]] = item.get("Value")
            
        log_entry = {
            "mpesa_trx_id": extracted.get("MpesaReceiptNumber"),
            "amount": extracted.get("Amount"),
            "phone_number": str(extracted.get("PhoneNumber")),
            "customer_name": "STK Push Payment",
            "account_ref": stk_callback_data.get("MerchantRequestID"),
            "created_at": request.headers.get('X-Vercel-Id', 'Just Now')
        }
        
        # Redis stores data beautifully as string JSON structures.
        # We push this dictionary into a Redis List named 'mpesa_pool'
        kv.rpush("mpesa_pool", json.dumps(log_entry))
            
    return jsonify({"ResultCode": 0, "ResultDesc": "Success"})

@app.route('/fetch-bridge-logs', methods=['GET'])
def fetch_bridge_logs():
    # 🟢 CRITICAL SAFETY CHECK FIRST
    if kv is None:
        return jsonify({
            "status": "error",
            "message": "The Redis client 'kv' is not initialized because the KV_URL environment variable is missing on Vercel.",
            "logs": []
        }), 200 # Keeping it 200 so your local browser reads this JSON notice easily

    try:
        raw_logs = kv.lrange("mpesa_pool", 0, -1) or []
        parsed_logs = [json.loads(log) for log in raw_logs]
        
        if raw_logs:
            kv.delete("mpesa_pool")
            
        return jsonify({"status": "success", "logs": parsed_logs})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Redis Error: {str(e)}", "logs": []}), 200

import os
from flask import Flask, request, jsonify
import redis
import json

app = Flask(__name__)

KV_URL = os.environ.get("KV_URL")

kv = None
if KV_URL:
    # Vercel's injected URL might start with 'redis://'. 
    # If it does, we patch it to 'rediss://' for secure SSL connectivity required by Upstash/Vercel.
    if KV_URL.startswith("redis://"):
        KV_URL = KV_URL.replace("redis://", "rediss://", 1)
        
    kv = redis.Redis.from_url(KV_URL, decode_responses=True)

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
    # 1. Fetch all records from our Redis list (from index 0 to -1 means everything)
    raw_logs = kv.lrange("mpesa_pool", 0, -1) or []
    
    # 2. Parse the JSON strings back into native Python dictionaries
    parsed_logs = [json.loads(log) for log in raw_logs]
    
    # 3. Clear the pool instantly so they are never fetched twice
    kv.delete("mpesa_pool")
    
    return jsonify({"status": "success", "logs": parsed_logs})

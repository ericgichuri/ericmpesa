from flask import Flask, request, jsonify
from vercel_kv import KV

app = Flask(__name__)
kv = KV() # Uses Vercel's built-in storage environment variables automatically

@app.route('/mpesa/stk-callback', methods=['POST'])
def stk_callback():
    data = request.get_json()
    stk_callback_data = data.get("Body", {}).get("stkCallback", {})
    
    if stk_callback_data.get("ResultCode") == 0:
        metadata = stk_callback_data.get("CallbackMetadata", {}).get("Item", [])
        
        extracted = {}
        for item in metadata:
            extracted[item["Name"]] = item.get("Value")
            
        # Format the exact JSON package your local app needs
        log_entry = {
            "mpesa_trx_id": extracted.get("MpesaReceiptNumber"),
            "amount": extracted.get("Amount"),
            "phone_number": str(extracted.get("PhoneNumber")),
            "customer_name": "STK Push Payment",
            "account_ref": stk_callback_data.get("MerchantRequestID"),
            "created_at": request.headers.get('X-Vercel-Id', 'Just Now') # Quick timestamp alternative
        }
        
        # Pull existing list from Vercel KV, append new JSON, and save back
        logs = kv.get("mpesa_pool") or []
        logs.append(log_entry)
        kv.set("mpesa_pool", logs)
            
    return jsonify({"ResultCode": 0, "ResultDesc": "Success"})

@app.route('/fetch-bridge-logs', methods=['GET'])
def fetch_bridge_logs():
    # 1. Grab all the raw JSON payloads waiting in the pool
    logs = kv.get("mpesa_pool") or []
    
    # 2. Clear the pool instantly so they are never fetched twice
    kv.set("mpesa_pool", [])
    
    return jsonify({"status": "success", "logs": logs})

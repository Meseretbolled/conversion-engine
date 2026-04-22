import os
import africastalking

africastalking.initialize(os.getenv("AT_USERNAME","sandbox"), os.getenv("AT_API_KEY",""))
sms = africastalking.SMS
_sender_id = os.getenv("AT_SENDER_ID", None)

def send_sms(to_number, message, prospect_id=""):
    if len(message) > 459:
        message = message[:456] + "..."
    kwargs = {"message": message, "recipients": [to_number]}
    if _sender_id:
        kwargs["sender_id"] = _sender_id
    response = sms.send(**kwargs)
    recipients = response.get("SMSMessageData", {}).get("Recipients", [])
    result = {"prospect_id":prospect_id,"to":to_number,"message":message,"status":"unknown","message_id":None}
    if recipients:
        r = recipients[0]
        result["status"] = r.get("status","unknown")
        result["message_id"] = r.get("messageId")
        result["cost"] = r.get("cost")
    return result

def handle_stop_command(phone_number, prospect_id=""):
    return {"prospect_id":prospect_id,"phone":phone_number,"opted_out":True,"channel":"sms"}

def parse_inbound(payload):
    text = (payload.get("text") or "").strip()
    return {
        "from_number": payload.get("from",""),
        "to_number":   payload.get("to",""),
        "text":        text,
        "is_stop":     text.upper() in ("STOP","UNSUBSCRIBE","UNSUB","CANCEL","END"),
        "is_help":     text.upper() in ("HELP","INFO"),
        "link_id":     payload.get("linkId"),
        "date":        payload.get("date"),
    }

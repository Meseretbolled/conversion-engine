import os, urllib.parse
import httpx
from datetime import datetime, timedelta

BASE_URL = os.getenv("CALCOM_BASE_URL", "http://localhost:3000")
API_KEY = os.getenv("CALCOM_API_KEY", "")
EVENT_TYPE_ID = int(os.getenv("CALCOM_EVENT_TYPE_ID", "1"))

def _headers():
    return {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

def get_available_slots(event_type_id=None, days_ahead=7):
    etype = event_type_id or EVENT_TYPE_ID
    start = datetime.utcnow().isoformat() + "Z"
    end = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + "Z"
    try:
        r = httpx.get(f"{BASE_URL}/api/v1/slots/available", headers=_headers(),
            params={"eventTypeId":etype,"startTime":start,"endTime":end}, timeout=10)
        r.raise_for_status()
        data = r.json()
        slots = []
        for day_slots in data.get("slots",{}).values():
            for slot in day_slots:
                slots.append({"start":slot.get("time"),"end":None})
        return slots[:10]
    except Exception as e:
        return [{"error":str(e)}]

def create_booking(prospect_name, prospect_email, start_time, context_note="", event_type_id=None, timezone="UTC"):
    etype = event_type_id or EVENT_TYPE_ID
    payload = {"eventTypeId":etype,"start":start_time,"timeZone":timezone,"language":"en",
        "responses":{"name":prospect_name,"email":prospect_email,"notes":context_note[:500]},
        "metadata":{"source":"tenacious-conversion-engine"}}
    try:
        r = httpx.post(f"{BASE_URL}/api/v1/bookings", headers=_headers(), json=payload, timeout=15)
        r.raise_for_status()
        data = r.json()
        booking = data.get("booking", data)
        return {"uid":booking.get("uid"),"start_time":booking.get("startTime") or start_time,
            "meeting_url":booking.get("meetingUrl") or booking.get("videoCallUrl"),
            "calendar_event_id":booking.get("id"),"attendees":booking.get("attendees",[]),"status":"confirmed"}
    except Exception as e:
        return {"error":str(e),"status":"failed"}

def get_booking_link_for_prospect(prospect_name, prospect_email, context_note=""):
    params = urllib.parse.urlencode({"name":prospect_name,"email":prospect_email,"notes":context_note[:200]})
    return f"{BASE_URL}/tenacious/discovery-call?{params}"

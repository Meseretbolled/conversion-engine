import os
from datetime import datetime
from typing import Optional
from hubspot import HubSpot
from hubspot.crm.contacts import SimplePublicObjectInputForCreate
from hubspot.crm.contacts.exceptions import ApiException

_client: Optional[HubSpot] = None

def get_client() -> HubSpot:
    global _client
    if _client is None:
        token = os.environ.get("HUBSPOT_ACCESS_TOKEN")
        if not token:
            raise ValueError("HUBSPOT_ACCESS_TOKEN not set")
        _client = HubSpot(access_token=token)
    return _client

def upsert_contact(email, first_name="", last_name="", company="", phone="",
                   job_title="", crunchbase_id="", icp_segment=0, ai_maturity_score=0, lifecycle_stage="lead"):
    client = get_client()
    properties = {k:v for k,v in {
        "email":email,"firstname":first_name,"lastname":last_name,"company":company,
        "phone":phone,"jobtitle":job_title,"lifecyclestage":lifecycle_stage,
        "crunchbase_id":crunchbase_id,"icp_segment":str(icp_segment),
        "ai_maturity_score":str(ai_maturity_score),
        "last_enriched_at":datetime.utcnow().isoformat(),
    }.items() if v}
    try:
        search = client.crm.contacts.search_api.do_search(public_object_search_request={
            "filters":[{"propertyName":"email","operator":"EQ","value":email}],"limit":1})
        if search.results:
            cid = search.results[0].id
            client.crm.contacts.basic_api.update(contact_id=cid,
                simple_public_object_input={"properties":properties})
            return {"id":cid,"action":"updated","email":email}
        result = client.crm.contacts.basic_api.create(
            simple_public_object_input_for_create=SimplePublicObjectInputForCreate(properties=properties))
        return {"id":result.id,"action":"created","email":email}
    except ApiException as e:
        return {"error":str(e),"email":email}

def log_email_sent(contact_id, subject, body, message_id, segment, pitch_variant):
    client = get_client()
    note_body = f"[OUTBOUND EMAIL]\nMessage ID: {message_id}\nSubject: {subject}\nSegment: {segment}\nVariant: {pitch_variant}\n\n{body[:500]}"
    try:
        note = client.crm.objects.notes.basic_api.create(
            simple_public_object_input_for_create=SimplePublicObjectInputForCreate(
                properties={"hs_note_body":note_body,"hs_timestamp":datetime.utcnow().isoformat()}))
        client.crm.objects.notes.associations_api.create(
            note_id=note.id,to_object_type="contacts",to_object_id=contact_id,association_type="note_to_contact")
        return {"note_id":note.id,"status":"logged"}
    except ApiException as e:
        return {"error":str(e)}

def log_sms_event(contact_id, direction, message):
    client = get_client()
    note_body = f"[SMS {direction.upper()}]\n{message[:300]}"
    try:
        note = client.crm.objects.notes.basic_api.create(
            simple_public_object_input_for_create=SimplePublicObjectInputForCreate(
                properties={"hs_note_body":note_body,"hs_timestamp":datetime.utcnow().isoformat()}))
        client.crm.objects.notes.associations_api.create(
            note_id=note.id,to_object_type="contacts",to_object_id=contact_id,association_type="note_to_contact")
        return {"note_id":note.id,"status":"logged"}
    except ApiException as e:
        return {"error":str(e)}

def log_booking(contact_id, booking_url, event_time):
    client = get_client()
    try:
        client.crm.contacts.basic_api.update(contact_id=contact_id,
            simple_public_object_input={"properties":{
                "lifecyclestage":"opportunity","discovery_call_url":booking_url,
                "discovery_call_time":event_time,"last_enriched_at":datetime.utcnow().isoformat()}})
        return {"status":"updated","contact_id":contact_id}
    except ApiException as e:
        return {"error":str(e)}

#!/bin/bash
# Tenacious Conversion Engine — Full End-to-End Test Script
# Run this after deploying to Render

SERVER="https://conversion-engine10.onrender.com"
EMAIL="meseretbolled@gmail.com"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo "=================================================="
echo " TENACIOUS CONVERSION ENGINE — E2E TEST SUITE"
echo "=================================================="
echo ""

# ── TEST 1: Render Health ─────────────────────────────────────────────────────
echo -e "${BLUE}TEST 1: Render Server Health${NC}"
HEALTH=$(curl -s "$SERVER/health" 2>/dev/null)
if echo "$HEALTH" | grep -q '"ok"'; then
  echo -e "${GREEN}✅ PASS — Server live: $HEALTH${NC}"
else
  echo -e "${RED}❌ FAIL — Server not responding: $HEALTH${NC}"
  echo "   → Check render.com → conversion-engine10 → Logs"
fi
echo ""

# ── TEST 2: Companies API ─────────────────────────────────────────────────────
echo -e "${BLUE}TEST 2: Companies API (Crunchbase CSV)${NC}"
COMPANIES=$(curl -s "$SERVER/api/companies?search=stripe&limit=5" 2>/dev/null)
COUNT=$(echo "$COMPANIES" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('companies',[])))" 2>/dev/null)
if [ "$COUNT" -gt "0" ] 2>/dev/null; then
  echo -e "${GREEN}✅ PASS — Found $COUNT companies matching 'stripe'${NC}"
else
  echo -e "${YELLOW}⚠️  PARTIAL — API responded but no Stripe match (OK if not in CSV)${NC}"
  echo "   Companies response: $(echo $COMPANIES | head -c 200)"
fi
echo ""

# ── TEST 3: Trigger Outreach Pipeline ────────────────────────────────────────
echo -e "${BLUE}TEST 3: Trigger Outreach Pipeline${NC}"
echo "   Triggering for Stripe / Alex / CTO..."
TRIGGER=$(curl -s -X POST "$SERVER/outreach/prospect" \
  -H "Content-Type: application/json" \
  -d '{
    "company_name": "Stripe",
    "prospect_email": "'$EMAIL'",
    "prospect_first_name": "Alex",
    "prospect_last_name": "Smith",
    "prospect_title": "CTO",
    "skip_scraping": true
  }' 2>/dev/null)
PROSPECT_ID=$(echo "$TRIGGER" | python3 -c "import json,sys; print(json.load(sys.stdin).get('prospect_id',''))" 2>/dev/null)
if [ -n "$PROSPECT_ID" ]; then
  echo -e "${GREEN}✅ PASS — Pipeline queued | prospect_id: $PROSPECT_ID${NC}"
  echo "   → Waiting 15 seconds for pipeline to complete..."
  sleep 15
else
  echo -e "${RED}❌ FAIL — No prospect_id returned: $TRIGGER${NC}"
fi
echo ""

# ── TEST 4: Prospect Registry ─────────────────────────────────────────────────
if [ -n "$PROSPECT_ID" ]; then
  echo -e "${BLUE}TEST 4: Prospect Registry${NC}"
  PROSPECT=$(curl -s "$SERVER/api/prospect/$PROSPECT_ID" 2>/dev/null)
  if echo "$PROSPECT" | grep -q '"company"'; then
    EMAIL_STORED=$(echo "$PROSPECT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('email',''))" 2>/dev/null)
    ICP=$(echo "$PROSPECT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('icp',{}).get('segment_name','unknown'))" 2>/dev/null)
    echo -e "${GREEN}✅ PASS — Prospect stored | email: $EMAIL_STORED | ICP: $ICP${NC}"
  else
    echo -e "${YELLOW}⚠️  Prospect not in registry yet (pipeline may still be running)${NC}"
    echo "   Response: $(echo $PROSPECT | head -c 200)"
  fi
  echo ""
fi

# ── TEST 5: Email Reply Webhook ────────────────────────────────────────────────
if [ -n "$PROSPECT_ID" ]; then
  echo -e "${BLUE}TEST 5: Email Reply Webhook (simulate prospect reply)${NC}"
  REPLY=$(curl -s -X POST "$SERVER/webhooks/email/reply" \
    -H "Content-Type: application/json" \
    -d '{
      "type": "email.received",
      "data": {
        "email_id": "test_'$PROSPECT_ID'",
        "from": "alex@stripe.com",
        "to": ["'$PROSPECT_ID'@ustoimeleo.resend.app"],
        "subject": "Re: Request: 15 minutes on engineering cost reduction",
        "text": "Interesting. Can you tell me more about pricing and timeline?",
        "tags": [{"name": "prospect_id", "value": "'$PROSPECT_ID'"}]
      }
    }' 2>/dev/null)
  if echo "$REPLY" | grep -q '"handled"'; then
    ACTION=$(echo "$REPLY" | python3 -c "import json,sys; print(json.load(sys.stdin).get('action',''))" 2>/dev/null)
    echo -e "${GREEN}✅ PASS — Reply handled | action: $ACTION${NC}"
    echo "   → Check Gmail for agent follow-up email (arrives in ~5s)"
  else
    echo -e "${RED}❌ FAIL — Reply not handled: $REPLY${NC}"
  fi
  echo ""
fi

# ── TEST 6: SMS Webhook ────────────────────────────────────────────────────────
echo -e "${BLUE}TEST 6: SMS Inbound Webhook${NC}"
SMS=$(curl -s -X POST "$SERVER/webhooks/sms/inbound" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "from=%2B251952677995&to=21271&text=Hello+Tenacious&date=2026-04-25" 2>/dev/null)
if echo "$SMS" | python3 -c "import json,sys; d=json.load(sys.stdin); exit(0 if d.get('status') else 1)" 2>/dev/null; then
  STATUS=$(echo "$SMS" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" 2>/dev/null)
  echo -e "${GREEN}✅ PASS — SMS webhook returned status: $STATUS${NC}"
else
  echo -e "${YELLOW}⚠️  SMS webhook response: $(echo $SMS | head -c 200)${NC}"
fi
echo ""

# ── TEST 7: Booking Webhook ────────────────────────────────────────────────────
echo -e "${BLUE}TEST 7: Cal.com Booking Webhook${NC}"
BOOKING=$(curl -s -X POST "$SERVER/webhooks/calcom/booking" \
  -H "Content-Type: application/json" \
  -d '{
    "triggerEvent": "BOOKING_CREATED",
    "payload": {
      "uid": "test-booking-123",
      "startTime": "2026-04-30T14:00:00Z",
      "attendees": [{"email": "'$EMAIL'", "name": "Alex Smith"}],
      "title": "Tenacious Discovery Call"
    }
  }' 2>/dev/null)
if echo "$BOOKING" | grep -q '"status"'; then
  echo -e "${GREEN}✅ PASS — Cal.com webhook handled: $BOOKING${NC}"
else
  echo -e "${YELLOW}⚠️  Cal.com webhook: $(echo $BOOKING | head -c 200)${NC}"
fi
echo ""

echo "=================================================="
echo " MANUAL CHECKS (do these now):"
echo "=================================================="
echo ""
echo "📧 GMAIL:"
echo "   → Open mail.google.com"
echo "   → Check for email from onboarding@resend.dev"
echo "   → Subject should reference Stripe layoff signal"
echo "   → Should contain Cal.com booking link"
echo "   → After reply test above, check for agent follow-up"
echo ""
echo "🏢 HUBSPOT:"
echo "   → Open app-eu1.hubspot.com"
echo "   → Go to tenacious-test → Contacts"
echo "   → Search 'Alex' → confirm contact exists"
echo "   → Check custom properties: icp_segment, ai_maturity_score"
echo "   → Check Activities tab for email sent note"
echo ""
echo "📈 LANGFUSE:"
echo "   → Open cloud.langfuse.com"
echo "   → Go to tenacious-ce → Tracing"
echo "   → Should show new outreach_pipeline trace"
echo "   → Check p50/p95 latency in Home dashboard"
echo ""
echo "🌐 RENDER:"
echo "   → Open render.com → conversion-engine10 → Logs"
echo "   → Confirm no errors in latest deploy"
echo "   → Look for: ICP: Segment X (high), Email sent, HubSpot contact"
echo ""
echo "📅 CAL.COM:"
echo "   → Open cal.com/meseret-bolled-pxprep/tenacious-discovery-call"
echo "   → Confirm booking page is live and shows available slots"
echo ""
echo "📱 RESEND:"
echo "   → Open resend.com → Emails"
echo "   → Confirm latest email shows status: Delivered"
echo "   → Check reply_to field shows prospect_id@ustoimeleo.resend.app"
echo ""
if [ -n "$PROSPECT_ID" ]; then
  echo "🆔 YOUR PROSPECT ID FOR THIS RUN: $PROSPECT_ID"
  echo "   Use this to simulate more replies:"
  echo ""
  echo "   curl -s -X POST $SERVER/webhooks/email/reply \\"
  echo "     -H 'Content-Type: application/json' \\"
  echo "     -d '{"
  echo "       \"type\": \"email.received\","
  echo "       \"data\": {"
  echo "         \"to\": [\"$PROSPECT_ID@ustoimeleo.resend.app\"],"
  echo "         \"text\": \"Can we book a call for Thursday?\","
  echo "         \"tags\": [{\"name\": \"prospect_id\", \"value\": \"$PROSPECT_ID\"}]"
  echo "       }"
  echo "     }'"
fi
echo ""
echo "Done! Fix any ❌ before the CEO presentation."
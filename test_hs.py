import os, sys

# Read .env manually
env_path = os.path.expanduser('~/Documents/conversion-engine/.env')
try:
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, _, v = line.partition('=')
                os.environ.setdefault(k.strip(), v.strip())
except:
    print("Could not read .env")

token = os.environ.get("HUBSPOT_ACCESS_TOKEN", "")
print(f"Token: {token[:25]}..." if token else "NO TOKEN SET")
if not token:
    sys.exit(1)

from hubspot import HubSpot
from hubspot.crm.contacts import SimplePublicObjectInputForCreate

client = HubSpot(access_token=token)

try:
    result = client.crm.contacts.basic_api.create(
        simple_public_object_input_for_create=SimplePublicObjectInputForCreate(
            properties={
                "email": "test_diag_2026@tenacious.com",
                "firstname": "Test",
                "company": "Snap",
                "lifecyclestage": "lead",
            }
        )
    )
    print(f"Contact created: {result.id}")
except Exception as e:
    print(f"Error: {e}")
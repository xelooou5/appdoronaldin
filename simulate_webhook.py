"""
simulate_webhook.py

Utility to POST a fake Telegram update to your bot webhook URL for testing.
Usage examples (PowerShell):

$env:WEBHOOK_TEST_URL = "https://appdoronaldin.up.railway.app/webhook/<YOUR_TOKEN_OR_PATH>"
python .\simulate_webhook.py

Or pass URL on command line:
python .\simulate_webhook.py https://appdoronaldin.up.railway.app/webhook/...

The script sends a minimal update with a `/ping` text message.
"""
import sys
import json
import time
import requests

SAMPLE_UPDATE = {
    "update_id": int(time.time()),
    "message": {
        "message_id": 1,
        "date": int(time.time()),
        "chat": {"id": 123456789, "type": "private"},
        "from": {"id": 123456789, "is_bot": False, "first_name": "Test", "username": "testuser"},
        "text": "/ping"
    }
}


def main():
    url = None
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        import os
        url = os.getenv("WEBHOOK_TEST_URL")
    if not url:
        print("Usage: set WEBHOOK_TEST_URL or pass URL as first arg. Example:")
        print("python simulate_webhook.py https://appdoronaldin.up.railway.app/webhook/<token>")
        sys.exit(2)

    headers = {"Content-Type": "application/json"}
    print("Posting sample update to {} ...".format(url))
    try:
        resp = requests.post(url, data=json.dumps(SAMPLE_UPDATE), headers=headers, timeout=10)
        print("Status:", resp.status_code)
        print(resp.text)
    except Exception as e:
        print("Request failed:", e)


if __name__ == '__main__':
    main()


import json, base64

with open("firebase/smart-mailbox-2f172-firebase-adminsdk-fbsvc-09169524f0.json", "r", encoding="utf-8") as f:
    raw = json.load(f)

encoded = base64.b64encode(json.dumps(raw).encode("utf-8")).decode("utf-8")
print(encoded)
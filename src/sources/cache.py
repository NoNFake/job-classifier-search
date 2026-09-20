import hashlib, json, time
from pathlib import Path
import requests

CACHE = Path(".cache")
TTL = 3600

def fetch(url, headers, ttl=TTL):
    key = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".json")
    if key.exists() and time.time() - key.stat().st_mtime < ttl:
        return json.loads(key.read_text())
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    CACHE.mkdir(exist_ok=True)
    key.write_text(r.text)
    return r.json()
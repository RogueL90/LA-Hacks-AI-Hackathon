"""Smoke test for the Space Service: runs every endpoint in-process and prints a summary.

Run from space_service/:  python test_local.py
"""
from collections import Counter

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

assert client.get("/health").json() == {"ok": True}

result = client.post("/spaces/build", json={"job_id": "job_local_01", "media_urls": []}).json()
assert result["ok"], result
space = result["space"]
print(f"space_id={space['space_id']} scale={space['scale_method']} viewer={space['viewer_url']}")
print(f"rooms={len(space['rooms'])} doors={len(space['doors'])} objects={len(space['objects'])}")
print("object types:", dict(Counter(o["type"] for o in space["objects"])))

assert client.get(f"/spaces/{space['space_id']}").status_code == 200

overlays = [{"type": "pin", "data": {"object_id": "obj_rug_02", "severity": 4, "title": "Loose hallway runner"}}]
created = client.post(
    f"/spaces/{space['space_id']}/overlays",
    json={"mode": "elder", "overlays": overlays, "job_id": "job_local_01"},
).json()
ov_id = created["overlay_set_id"]
assert client.get(f"/spaces/{space['space_id']}/overlays/{ov_id}").json()["mode"] == "elder"
print(f"overlay_set_id={ov_id}")

png = client.get(f"/spaces/{space['space_id']}/snapshot.png?mode=elder&o={ov_id}")
assert png.headers["content-type"] == "image/png"

upload = client.post("/media/upload", files={"file": ("frame.jpg", b"fake-bytes", "image/jpeg")}).json()
print("upload url:", upload["url"])

print("ALL OK")

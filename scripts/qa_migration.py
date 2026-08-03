"""Black-box check for the explicit v3-to-v4 copy workflow."""

import json
from urllib.request import Request, urlopen


BASE = "http://127.0.0.1:18766"


def read_json(path: str, method: str = "GET"):
    request = Request(BASE + path, method=method)
    if method != "GET":
        request.add_header("Content-Type", "application/json")
        request.data = b"{}"
    with urlopen(request, timeout=10) as response:
        return json.load(response)


status = read_json("/api/migration/status")
assert status["available"], status["reason"]
expected = int(status["applications"])
assert expected > 0
report = read_json("/api/migration/import", "POST")
assert report["imported"]
applications = read_json("/api/applications")
assert len(applications) == expected, (len(applications), expected)
print(json.dumps({"discovered": expected, "imported": len(applications)}, ensure_ascii=False))

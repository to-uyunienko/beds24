"""テスト用の偽 Beds24 API（urlopen の差し替え）。"""
import io
import json
import urllib.error
import urllib.parse

LONG_LIFE = "long-life-token"
REFRESH = "refresh-token"
ACCESS = "access-token"


class FakeResponse:
    def __init__(self, status, body, headers=None):
        self.status = status
        self.headers = headers or {}
        self._body = json.dumps(body).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeBeds24:
    """properties / bookings / messages を持ち、Beds24 と同じ形でページ分けして返す。"""

    def __init__(self, properties=(), bookings=(), messages=(), page_size=2, fail_first=None, low_credit=False):
        self.properties = list(properties)
        self.bookings = list(bookings)
        self.messages = list(messages)
        self.page_size = page_size
        self.fail_first = dict(fail_first or {})  # {path: HTTPステータス} 最初の1回だけ失敗させる
        self.low_credit = low_credit
        self.calls = []

    def __call__(self, req, timeout=None):
        parsed = urllib.parse.urlparse(req.full_url)
        path = parsed.path.replace("/v2", "", 1)
        query = urllib.parse.parse_qs(parsed.query)
        headers = {k.lower(): v for k, v in req.header_items()}
        self.calls.append((path, query, headers))
        if path in self.fail_first:
            code = self.fail_first.pop(path)
            raise urllib.error.HTTPError(req.full_url, code, "error", {"x-five-min-limit-resets-in": "3"},
                                         io.BytesIO(b'{"success": false}'))
        if path == "/authentication/details":
            valid = headers.get("token") in (LONG_LIFE, ACCESS)
            return FakeResponse(200, {"validToken": valid, "token": {"scopes": ["read:bookings"]} if valid else {}})
        if path == "/authentication/token":
            if headers.get("refreshtoken") == REFRESH:
                return FakeResponse(200, {"token": ACCESS, "expiresIn": 86400})
            raise urllib.error.HTTPError(req.full_url, 401, "unauthorized", {}, io.BytesIO(b'{"success": false}'))
        if headers.get("token") not in (LONG_LIFE, ACCESS):
            raise urllib.error.HTTPError(req.full_url, 401, "unauthorized", {}, io.BytesIO(b'{"success": false}'))
        if path == "/properties":
            items = self.properties
        elif path == "/bookings":
            items = self._filter_bookings(query)
        elif path == "/bookings/messages":
            ids = {int(i) for i in query.get("bookingId", [])}
            items = [m for m in self.messages if not ids or m["bookingId"] in ids]
        else:
            raise urllib.error.HTTPError(req.full_url, 404, "not found", {}, io.BytesIO(b"{}"))
        page = int(query.get("page", ["1"])[0])
        chunk = items[(page - 1) * self.page_size: page * self.page_size]
        more = page * self.page_size < len(items)
        headers_out = {"x-five-min-limit-remaining": "3" if self.low_credit else "500",
                       "x-five-min-limit-resets-in": "7", "x-request-cost": "1"}
        return FakeResponse(200, {"success": True, "count": len(chunk), "data": chunk,
                                  "pages": {"nextPageExists": more, "nextPageLink": None}}, headers_out)

    def _filter_bookings(self, query):
        items = self.bookings
        if "id" in query:
            ids = {int(i) for i in query["id"]}
            items = [b for b in items if b["id"] in ids]
        if "propertyId" in query:
            pids = {int(i) for i in query["propertyId"]}
            items = [b for b in items if b["propertyId"] in pids]
        if "departureFrom" in query:
            items = [b for b in items if b["departure"] >= query["departureFrom"][0]]
        if "status" in query:
            items = [b for b in items if b["status"] in query["status"]]
        return items

"""Beds24 API V2 の読み取り専用クライアント（Python 標準ライブラリのみ）。

キーは「長期トークン（読み取り専用）」「リフレッシュトークン」「招待コード」のどれでも受け付ける。
まずそのまま token ヘッダーで試し、無効ならリフレッシュトークン、次に招待コードとして短期トークンに交換する。

注意: Beds24 はリフレッシュトークンを交換するたびに新しいリフレッシュトークンを発行し、古いものを無効にする。
新しいトークンは on_new_refresh_token に渡すので、呼び出し側で必ず保存すること（失うとキーを作り直すしかない）。
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://api.beds24.com/v2"

# GET /bookings の status フィルタ。キャンセル・問い合わせも含めて全件取る。
ALL_BOOKING_STATUSES = ["confirmed", "new", "request", "cancelled", "black", "inquiry"]


class Beds24Error(Exception):
    pass


class Beds24Client:
    def __init__(self, key, base=API_BASE, urlopen=urllib.request.urlopen,
                 sleep=time.sleep, log=None, max_retries=5, on_new_refresh_token=None):
        self.key = key.strip()
        self.on_new_refresh_token = on_new_refresh_token
        self.base = base.rstrip("/")
        self.urlopen = urlopen
        self.sleep = sleep
        self.log = log or (lambda msg: None)
        self.max_retries = max_retries
        self.token = None
        self.token_details = None

    # ---- 低レベル ----

    def _call(self, path, params=None, headers=None):
        """GET を1回発行し (HTTPステータス, JSON) を返す。429/5xx/通信エラーは待って再試行する。"""
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)
        hdrs = {"accept": "application/json"}
        hdrs.update(headers or {})
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(url, headers=hdrs, method="GET")
            try:
                with self.urlopen(req, timeout=60) as resp:
                    body = resp.read().decode("utf-8")
                    self._respect_credit_limit(resp.headers)
                    return resp.status, _parse_json(body)
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace")
                if (e.code == 429 or e.code >= 500) and attempt < self.max_retries:
                    wait = _int_header(e.headers, "x-five-min-limit-resets-in") or min(60, 5 * 2 ** attempt)
                    self.log(f"HTTP {e.code} {path}: {wait}秒待って再試行します")
                    self.sleep(wait + 1)
                    continue
                return e.code, _parse_json(body)
            except urllib.error.URLError as e:
                if attempt < self.max_retries:
                    self.sleep(2 ** attempt)
                    continue
                raise Beds24Error(f"{path} に接続できません: {e.reason}") from None
        raise Beds24Error(f"{path}: 再試行の上限に達しました")

    def _respect_credit_limit(self, headers):
        """5分間のクレジット残量が少なくなったらリセットまで待つ。"""
        remaining = _int_header(headers, "x-five-min-limit-remaining")
        cost = _int_header(headers, "x-request-cost") or 1
        if remaining is not None and remaining <= max(5, cost * 2):
            wait = _int_header(headers, "x-five-min-limit-resets-in") or 60
            self.log(f"APIクレジット残り {remaining}: {wait}秒待機します")
            self.sleep(wait + 1)

    # ---- 認証 ----

    def authenticate(self):
        """キーの種類を判定して利用可能な token をセットし、種類（"token"/"refresh"/"invite"）を返す。"""
        status, data = self._call("/authentication/details", headers={"token": self.key})
        if status == 200 and isinstance(data, dict) and data.get("validToken"):
            self.token, self.token_details = self.key, data
            return "token"
        if self.on_new_refresh_token is None:
            raise Beds24Error("長期トークンではありません。リフレッシュトークン・招待コードは交換すると新しいキーが発行され"
                              "元のキーが無効になるため、保存先（on_new_refresh_token）を指定してください")
        for kind, path, header in (("refresh", "/authentication/token", "refreshToken"),
                                   ("invite", "/authentication/setup", "code")):
            status, data = self._call(path, headers={header: self.key})
            if status == 200 and isinstance(data, dict) and data.get("token"):
                if data.get("refreshToken"):
                    # 次の通信より前に保存する。古いキーはこの時点で無効になっている
                    self.on_new_refresh_token(data["refreshToken"])
                    self.key = data["refreshToken"]
                self.token = data["token"]
                s2, d2 = self._call("/authentication/details", headers={"token": self.token})
                self.token_details = d2 if s2 == 200 else None
                return kind
        raise Beds24Error(f"APIキーが受け付けられませんでした（HTTP {status}）: {_short(data)}")

    def scopes(self):
        d = self.token_details or {}
        return (d.get("token") or {}).get("scopes") or d.get("scopes") or []

    # ---- ページング付き GET ----

    def get_all(self, path, params=None, max_pages=500):
        if not self.token:
            raise Beds24Error("authenticate() を先に呼んでください")
        params = dict(params or {})
        items, page = [], 1
        while True:
            params["page"] = page
            status, data = self._call(path, params, headers={"token": self.token})
            if status != 200 or not isinstance(data, dict) or data.get("success") is False:
                raise Beds24Error(f"GET {path} が失敗しました（HTTP {status}）: {_short(data)}")
            batch = data.get("data") or []
            items.extend(batch)
            if not batch or not _has_next_page(data.get("pages"), page):
                return items
            page += 1
            if page > max_pages:
                self.log(f"GET {path}: {max_pages}ページで打ち切りました")
                return items

    # ---- エンドポイント ----

    def properties(self):
        return self.get_all("/properties", {"includeAllRooms": "true"})

    def bookings(self, property_ids=None, departure_from=None, statuses=ALL_BOOKING_STATUSES, booking_ids=None):
        params = {}
        if property_ids:
            params["propertyId"] = list(property_ids)
        if departure_from:
            params["departureFrom"] = departure_from
        if statuses:
            params["status"] = list(statuses)
        if booking_ids:
            params["id"] = list(booking_ids)
        return self.get_all("/bookings", params)

    def messages_for_bookings(self, booking_ids, batch_size=25):
        ids = sorted(set(booking_ids))
        out = []
        for i in range(0, len(ids), batch_size):
            out.extend(self.get_all("/bookings/messages", {"bookingId": ids[i:i + batch_size]}))
        return out

    def recent_messages(self, max_age_seconds, max_pages=50):
        """アカウント全体の直近メッセージ（maxAge は仕様上「秒」。取得後に必ず日時で再フィルタすること）。"""
        return self.get_all("/bookings/messages", {"maxAge": int(max_age_seconds)}, max_pages=max_pages)


def _has_next_page(pages, page):
    if isinstance(pages, dict):
        return bool(pages.get("nextPageExists"))
    if isinstance(pages, int):
        return page < pages
    return False


def _parse_json(body):
    try:
        return json.loads(body) if body else None
    except ValueError:
        return body


def _int_header(headers, name):
    try:
        return int(headers.get(name)) if headers and headers.get(name) is not None else None
    except (TypeError, ValueError):
        return None


def _short(data, limit=300):
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return text[:limit]

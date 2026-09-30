import csv
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import build_review
import fetch_messages
from beds24_tools.client import Beds24Client, Beds24Error
from beds24_tools.dataset import JST
from beds24_tools.topics import classify
from tests.fake_api import INVITE, LONG_LIFE, REFRESH, FakeBeds24


def iso(days_ago, hour=12):
    """Beds24 と同じ UTC の "Z" 付き表記で、JST の hour 時 days_ago 日前を返す。"""
    t = datetime.now(JST).replace(hour=hour, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def day(days_from_today):
    return (datetime.now(JST).date() + timedelta(days=days_from_today)).isoformat()


PROPERTIES = [
    {"id": 1, "name": "Sample House", "roomTypes": [{"id": 11, "name": "201"}, {"id": 12, "name": "301"}]},
    {"id": 2, "name": "Other House", "roomTypes": [{"id": 21, "name": "Room A"}]},
    {"id": 3, "name": "Unit House", "groupKeywords": ["テスト合同会社"],
     "roomTypes": [{"id": 31, "name": "1ベッドルーム", "qty": 2, "units": [{"id": 1, "name": "501"}, {"id": 2, "name": "502"}]}]},
]
BOOKINGS = [
    {"id": 100, "propertyId": 1, "roomId": 11, "status": "confirmed", "arrival": day(-10), "departure": day(-7),
     "numAdult": 2, "numChild": 0, "referer": "Airbnb", "firstName": "Taro", "email": "taro@example.com"},
    {"id": 101, "propertyId": 1, "roomId": 12, "status": "cancelled", "arrival": day(5), "departure": day(7),
     "numAdult": 3, "numChild": 1, "channel": "booking"},
    {"id": 102, "propertyId": 1, "roomId": 12, "status": "confirmed", "arrival": day(-120), "departure": day(-118)},
    {"id": 200, "propertyId": 2, "roomId": 21, "status": "confirmed", "arrival": day(-3), "departure": day(-1)},
    {"id": 300, "propertyId": 3, "roomId": 31, "unitId": 2, "status": "confirmed", "arrival": day(1), "departure": day(3)},
]
MESSAGES = [
    {"id": 1, "bookingId": 100, "source": "guest", "time": iso(12), "message": "Can we leave our luggage before check-in?"},
    {"id": 2, "bookingId": 100, "source": "host", "time": iso(12, 13), "message": "Yes, there is a luggage area on 1F."},
    {"id": 3, "bookingId": 100, "source": "internalNote", "time": iso(12, 14), "message": "オーナー確認済み"},
    {"id": 4, "bookingId": 100, "source": "guest", "time": iso(11), "message": "Thanks!"},
    {"id": 5, "bookingId": 101, "source": "guest", "time": iso(2), "message": "Wi-Fiのパスワードを教えてください"},
    {"id": 6, "bookingId": 101, "source": "guest", "time": iso(45), "message": "too old: outside the window"},
    {"id": 7, "bookingId": 102, "source": "guest", "time": iso(3), "message": "old booking, message not fetched by default"},
    {"id": 8, "bookingId": 200, "source": "guest", "time": iso(2), "message": "other property"},
    {"id": 9, "bookingId": 101, "source": "host", "time": iso(1), "message": "Welcome! Check-in guide: door code 1234. Enjoy your stay!!"},
    {"id": 10, "bookingId": 100, "source": "host", "time": iso(10), "message": "Welcome! Check-in guide: door code 5678. Enjoy your stay!!"},
    {"id": 11, "bookingId": 300, "source": "guest", "time": iso(1), "message": "Is there parking nearby?"},
]


def client_for(api, key=LONG_LIFE, saved=None):
    return Beds24Client(key, urlopen=api, sleep=lambda s: api.calls.append(("sleep", s, None)),
                        on_new_refresh_token=(saved.append if saved is not None else None))


class ClientTest(unittest.TestCase):
    def test_long_life_token_is_used_directly(self):
        api = FakeBeds24()
        c = client_for(api)
        self.assertEqual(c.authenticate(), "token")
        self.assertEqual(c.token, LONG_LIFE)
        self.assertEqual(c.scopes(), ["read:bookings"])

    def test_refresh_token_is_exchanged_and_the_new_one_is_handed_over(self):
        api, saved = FakeBeds24(), []
        c = client_for(api, REFRESH, saved)
        self.assertEqual(c.authenticate(), "refresh")
        self.assertEqual(saved, [REFRESH + "-1"])
        self.assertEqual(client_for(api, saved[0], saved).authenticate(), "refresh")
        with self.assertRaises(Beds24Error):  # 使用済みの元のキーはもう使えない
            client_for(api, REFRESH, saved).authenticate()

    def test_refresh_token_is_not_used_without_a_place_to_save_the_new_one(self):
        api = FakeBeds24()
        with self.assertRaises(Beds24Error):
            client_for(api, REFRESH).authenticate()
        self.assertEqual(api.refresh_tokens, {REFRESH})

    def test_invite_code_is_exchanged(self):
        saved = []
        self.assertEqual(client_for(FakeBeds24(), INVITE, saved).authenticate(), "invite")
        self.assertEqual(len(saved), 1)

    def test_bad_key_raises(self):
        with self.assertRaises(Beds24Error):
            client_for(FakeBeds24(), "wrong", []).authenticate()

    def test_pages_are_followed_and_429_is_retried(self):
        api = FakeBeds24(properties=PROPERTIES * 3, page_size=2, fail_first={"/properties": 429})
        c = client_for(api)
        c.authenticate()
        self.assertEqual(len(c.properties()), len(PROPERTIES) * 3)
        self.assertIn(("sleep", 4, None), api.calls)  # x-five-min-limit-resets-in + 1

    def test_low_credit_waits_for_reset(self):
        api = FakeBeds24(properties=PROPERTIES, low_credit=True)
        c = client_for(api)
        c.authenticate()
        c.properties()
        self.assertIn(("sleep", 8, None), api.calls)


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = os.path.join(self.tmp.name, "out")

    def tearDown(self):
        self.tmp.cleanup()

    def fetch(self, *extra):
        api = FakeBeds24(PROPERTIES, BOOKINGS, MESSAGES)
        args = fetch_messages.build_parser().parse_args(["--name-contains", "sample", "--days", "30", "--out", self.out, *extra])
        self.assertEqual(fetch_messages.run(args, client_for(api)), 0)
        with open(os.path.join(self.out, "raw", "messages.json"), encoding="utf-8") as f:
            messages = json.load(f)
        with open(os.path.join(self.out, "raw", "bookings.json"), encoding="utf-8") as f:
            bookings = json.load(f)
        return api, messages, bookings

    def test_fetch_selects_property_window_and_drops_personal_data(self):
        api, messages, bookings = self.fetch()
        self.assertEqual(sorted(m["id"] for m in messages), [1, 2, 3, 4, 5, 9, 10])
        self.assertEqual(sorted(b["id"] for b in bookings), [100, 101])
        self.assertNotIn("firstName", bookings[0])
        self.assertNotIn("email", bookings[0])
        booking_query = next(q for p, q, _h in api.calls if p == "/bookings")
        self.assertEqual(booking_query["propertyId"], ["1"])
        self.assertIn("cancelled", booking_query["status"])
        with open(os.path.join(self.out, "threads.md"), encoding="utf-8") as f:
            threads = f.read()
        self.assertIn("Sample House / 201 | 予約 #100 | Airbnb", threads)
        self.assertNotIn("Taro", threads)

    def test_scan_max_age_picks_up_messages_on_old_bookings(self):
        api, messages, bookings = self.fetch("--scan-max-age")
        self.assertIn(7, [m["id"] for m in messages])
        self.assertNotIn(8, [m["id"] for m in messages])
        self.assertIn(102, [b["id"] for b in bookings])
        max_age = next(q for p, q, _h in api.calls if p == "/bookings/messages" and "maxAge" in q)["maxAge"][0]
        self.assertGreater(int(max_age), 30 * 86400 - 1)

    def test_key_file_is_rewritten_so_the_next_run_still_works(self):
        api = FakeBeds24(PROPERTIES, BOOKINGS, MESSAGES)
        key_file = os.path.join(self.tmp.name, "key.txt")
        with open(key_file, "w", encoding="utf-8") as f:
            f.write(REFRESH)
        argv = ["--key-file", key_file, "--name-contains", "sample", "--out", self.out]
        self.assertEqual(fetch_messages.main(argv, urlopen=api), 0)
        with open(key_file, encoding="utf-8") as f:
            self.assertEqual(f.read(), REFRESH + "-1")
        self.assertEqual(fetch_messages.main(argv, urlopen=api), 0)
        with open(key_file, encoding="utf-8") as f:
            self.assertEqual(f.read(), REFRESH + "-2")

    def test_group_keyword_selects_property_and_units_label_rooms(self):
        api = FakeBeds24(PROPERTIES, BOOKINGS, MESSAGES)
        args = fetch_messages.build_parser().parse_args(["--group", "テスト合同会社", "--out", self.out])
        self.assertEqual(fetch_messages.run(args, client_for(api)), 0)
        with open(os.path.join(self.out, "raw", "messages.json"), encoding="utf-8") as f:
            self.assertEqual([m["id"] for m in json.load(f)], [11])
        with open(os.path.join(self.out, "threads.md"), encoding="utf-8") as f:
            self.assertIn("## Unit House / 1ベッドルーム / 502 | 予約 #300", f.read())

    def test_room_name_selection_limits_rooms(self):
        api = FakeBeds24(PROPERTIES, BOOKINGS, MESSAGES)
        args = fetch_messages.build_parser().parse_args(["--name-contains", "301", "--out", self.out])
        self.assertEqual(fetch_messages.run(args, client_for(api)), 0)
        with open(os.path.join(self.out, "raw", "bookings.json"), encoding="utf-8") as f:
            self.assertEqual([b["id"] for b in json.load(f)], [101])

    def test_review_pairs_questions_with_answers_and_sheet(self):
        self.fetch()
        sheet = os.path.join(self.tmp.name, "sheet.csv")
        with open(sheet, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["施設名", "ID", "管理会社", "荷物預チェックイン前", "荷物預チェックアウト後", "Wi-Fi", "鍵"])
            w.writerow(["201 Sample House", "b01", "サンプル管理", "1階で預かり可", "1階で預かり可", "ハウスマニュアル参照", ""])
            w.writerow(["301 Sample House", "b02", "サンプル管理", "1階で預かり可", "1階で預かり可", "ハウスマニュアル参照", ""])
            w.writerow(["Other", "x01", "他社", "", "", "", ""])
            w.writerow(["301 Unit House", "u01", "サンプル管理", "", "", "", ""])  # 別施設の同じ部屋番号に紛れないこと
        self.assertEqual(build_review.main(["--data", self.out, "--sheet", sheet, "--company", "サンプル管理",
                                            "--template-min-count", "2"]), 0)
        with open(os.path.join(self.out, "review.md"), encoding="utf-8") as f:
            review = f.read()
        self.assertIn("### 荷物預け（IN前・OUT後）（1件）", review)
        self.assertIn("> 1階で預かり可", review)
        self.assertIn("Sample House / 201 (b01)", review)
        self.assertIn("**A**（", review)
        self.assertIn("）: Yes, there is a luggage area on 1F.", review)
        self.assertIn("）: オーナー確認済み", review)
        self.assertIn("**シートの記載「荷物預チェックイン前」「荷物預チェックアウト後」（b01, b02）**", review)
        self.assertIn("自動送信・テンプレート 1 種類", review)
        self.assertIn("）: [定型文T1]", review)  # 定型文は本文ではなく番号で示す
        with open(os.path.join(self.out, "templates.md"), encoding="utf-8") as f:
            templates = f.read()
        self.assertIn("## T1（2回: Sample House 2）", templates)
        with open(os.path.join(self.out, "conversations_Sample_House.md"), encoding="utf-8") as f:
            conversation = f.read()
        self.assertIn("H: [T1]", conversation)
        self.assertIn("G: Can we leave our luggage before check-in?", conversation)
        self.assertIn("全室で空欄の列: 鍵", review)
        with open(os.path.join(self.out, "qa_pairs.csv"), encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 3)
        wifi = next(r for r in rows if "Wi-Fi" in r["項目"])
        self.assertEqual(wifi["シートID"], "b02")


class TopicsTest(unittest.TestCase):
    def test_multilingual_examples(self):
        cases = {
            "Could you tell me the door code?": "鍵・入室方法",
            "チェックイン前に荷物を預けられますか？": "荷物預け（IN前・OUT後）",
            "我们的航班延误了，可能晚上12点到": "深夜到着",
            "수건을 더 받을 수 있을까요?": "タオル・リネン交換",
            "Is there a supermarket nearby?": "スーパー・コンビニ",
            "I think I left my charger in the room": "忘れ物",
            "Can I get a receipt?": "支払い・領収書",
        }
        for text, label in cases.items():
            self.assertIn(label, classify(text), text)

    def test_greeting_matches_nothing(self):
        self.assertEqual(classify("Thank you so much!"), [])


if __name__ == "__main__":
    unittest.main()

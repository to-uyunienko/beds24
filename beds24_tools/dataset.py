"""取得したデータ（properties / bookings / messages）の保存・読み込みとスレッド整形。"""
import csv
import json
import os
import re
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

SOURCE_LABELS = {"guest": "ゲスト", "host": "ホスト", "internalNote": "内部メモ", "system": "システム"}

# 予約データのうち分析に使う項目だけを保存する（氏名・連絡先などの個人情報は保存しない）
BOOKING_FIELDS = ["id", "masterId", "propertyId", "roomId", "unitId", "status", "subStatus",
                  "arrival", "departure", "numAdult", "numChild", "channel", "apiSource",
                  "referer", "bookingTime", "modifiedTime", "lang"]


def parse_time(value):
    """Beds24 の日時文字列を aware datetime に。タイムゾーンが無ければ UTC とみなす。"""
    if not value:
        return None
    s = str(value).strip().replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def fmt_jst(dt):
    return dt.astimezone(JST).strftime("%Y-%m-%d %H:%M") if dt else ""


def guess_lang(text):
    """文字種による簡易判定（ja / ko / zh / latin）。"""
    text = text or ""
    if re.search(r"[぀-ヿ]", text):
        return "ja"
    if re.search(r"[가-힯]", text):
        return "ko"
    if re.search(r"[一-鿿]", text):
        return "zh"
    if re.search(r"[A-Za-z]", text):
        return "latin"
    return "?"


def slim_booking(b):
    return {k: b[k] for k in BOOKING_FIELDS if k in b}


def slim_message(m):
    # 添付ファイル本体は保存しない（ファイル名・種類のみ）
    return {k: v for k, v in m.items() if k != "attachment"}


def rooms_of(prop):
    return prop.get("roomTypes") or prop.get("rooms") or []


def room_index(properties):
    """{roomId: (property, room)} の辞書。"""
    idx = {}
    for p in properties:
        for r in rooms_of(p):
            idx[r.get("id")] = (p, r)
    return idx


def room_label(properties_by_id, rooms_by_id, booking):
    """「施設名 / 部屋名 / 部屋番号（ユニット名）」。同じ部屋タイプに複数室ある場合はユニット名で区別する。"""
    prop = properties_by_id.get(booking.get("propertyId")) or {}
    room = (rooms_by_id.get(booking.get("roomId")) or (None, {}))[1]
    unit = next((u for u in room.get("units") or [] if u.get("id") == booking.get("unitId")), {})
    names = [n for n in (prop.get("name"), room.get("name"), unit.get("name")) if n]
    return " / ".join(names) or f"property {booking.get('propertyId')} room {booking.get('roomId')}"


def channel_of(booking):
    return booking.get("channel") or booking.get("apiSource") or booking.get("referer") or ""


def save_dataset(out_dir, properties, bookings, messages, run_info):
    raw = os.path.join(out_dir, "raw")
    os.makedirs(raw, exist_ok=True)
    _dump(os.path.join(raw, "properties.json"), properties)
    _dump(os.path.join(raw, "bookings.json"), bookings)
    _dump(os.path.join(raw, "messages.json"), messages)
    _dump(os.path.join(out_dir, "run_info.json"), run_info)


def load_dataset(out_dir):
    raw = os.path.join(out_dir, "raw")
    return (_load(os.path.join(raw, "properties.json")),
            _load(os.path.join(raw, "bookings.json")),
            _load(os.path.join(raw, "messages.json")))


def build_threads(properties, bookings, messages):
    """予約ごとにメッセージを時系列で並べたスレッドのリストを返す（最初のメッセージが古い順）。"""
    props = {p.get("id"): p for p in properties}
    rooms = room_index(properties)
    by_booking = {}
    for m in messages:
        by_booking.setdefault(m.get("bookingId"), []).append(m)
    bookings_by_id = {b.get("id"): b for b in bookings}
    threads = []
    for bid, msgs in by_booking.items():
        msgs.sort(key=lambda m: (parse_time(m.get("time")) or datetime.min.replace(tzinfo=timezone.utc), m.get("id") or 0))
        b = bookings_by_id.get(bid, {"id": bid})
        threads.append({
            "booking": b,
            "room": room_label(props, rooms, b),
            "channel": channel_of(b),
            "lang": guess_lang(" ".join(m.get("message") or "" for m in msgs if m.get("source") == "guest")),
            "messages": msgs,
        })
    threads.sort(key=lambda t: parse_time(t["messages"][0].get("time")) or datetime.min.replace(tzinfo=timezone.utc))
    return threads


def write_threads_md(path, threads, title):
    counts = {}
    for t in threads:
        for m in t["messages"]:
            counts[m.get("source")] = counts.get(m.get("source"), 0) + 1
    total = sum(counts.values())
    breakdown = " / ".join(f"{SOURCE_LABELS.get(k, k)} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))
    lines = [f"# {title}", "", f"スレッド数: {len(threads)} / メッセージ数: {total}（{breakdown}）", ""]
    for t in threads:
        b = t["booking"]
        lines.append(f"## {t['room']} | 予約 #{b.get('id')} | {t['channel'] or '-'} | "
                     f"{b.get('arrival', '?')} → {b.get('departure', '?')} | "
                     f"大人{b.get('numAdult', '?')} 子{b.get('numChild', '?')} | {b.get('status', '?')} | 言語: {t['lang']}")
        lines.append("")
        for m in t["messages"]:
            who = SOURCE_LABELS.get(m.get("source"), m.get("source") or "?")
            text = (m.get("message") or "").strip() or "（本文なし）"
            if m.get("attachmentName"):
                text += f"\n[添付: {m['attachmentName']}]"
            body = text.replace("\n", "\n    ")
            lines.append(f"- {fmt_jst(parse_time(m.get('time')))} **{who}**: {body}")
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_messages_csv(path, threads):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["日時(JST)", "部屋", "予約ID", "チャネル", "チェックイン", "チェックアウト", "ステータス",
                    "送信者", "言語", "メッセージ", "メッセージID"])
        for t in threads:
            b = t["booking"]
            for m in t["messages"]:
                w.writerow([fmt_jst(parse_time(m.get("time"))), t["room"], b.get("id"), t["channel"],
                            b.get("arrival", ""), b.get("departure", ""), b.get("status", ""),
                            SOURCE_LABELS.get(m.get("source"), m.get("source")), guess_lang(m.get("message")),
                            m.get("message") or "", m.get("id")])


def _dump(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

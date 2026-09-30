#!/usr/bin/env python3
"""Beds24 から指定期間のゲストメッセージを取得し、予約ごとのスレッドとして保存する。

使い方（詳しくは README.md）:
  export BEDS24_TOKEN='（APIキー）'          # または --key-file ファイルパス
  python3 fetch_messages.py --list-properties
  python3 fetch_messages.py --name-contains "Sample House" --days 30 --out out/sample

出力（--out 配下。公開リポジトリにはコミットしないこと）:
  threads.md      予約ごとの会話ログ（読む用）
  messages.csv    1メッセージ1行（Excel で開ける UTF-8 BOM 付き）
  raw/*.json      取得データ（予約は個人情報を除いた項目のみ）
  run_info.json   取得条件と件数
"""
import argparse
import os
import sys
from datetime import datetime, time, timedelta

from beds24_tools.client import ALL_BOOKING_STATUSES, Beds24Client, Beds24Error
from beds24_tools.dataset import (JST, build_threads, parse_time, rooms_of, save_dataset, slim_booking,
                                  slim_message, write_messages_csv, write_threads_md)


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--key-file", help="APIキーを書いたファイル（未指定なら環境変数 BEDS24_TOKEN、次に ./.beds24_token）")
    ap.add_argument("--list-properties", action="store_true", help="施設・部屋の一覧を表示して終了")
    ap.add_argument("--name-contains", nargs="*", default=[], help="施設名または部屋名に含まれる文字列（複数可、OR）")
    ap.add_argument("--property-id", nargs="*", type=int, default=[], help="対象の施設ID（複数可）")
    ap.add_argument("--room-id", nargs="*", type=int, default=[], help="対象の部屋ID（複数可）")
    ap.add_argument("--days", type=int, default=30, help="何日前からのメッセージを取るか（既定: 30）")
    ap.add_argument("--since", help="開始日 YYYY-MM-DD（JST。指定時は --days より優先）")
    ap.add_argument("--until", help="終了日 YYYY-MM-DD（JST、この日を含む。既定: 今日）")
    ap.add_argument("--departure-buffer-days", type=int, default=30,
                    help="開始日の何日前までに退室した予約まで遡るか（退室後の忘れ物連絡などを拾うため。既定: 30）")
    ap.add_argument("--scan-max-age", action="store_true",
                    help="maxAge でアカウント全体の直近メッセージも取得し、古い予約へのメッセージも拾う")
    ap.add_argument("--out", help="出力フォルダ")
    return ap


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):  # Windows のコンソールで絵文字入りの名前が出ても落ちないように
        stream.reconfigure(errors="replace")
    ap = build_parser()
    args = ap.parse_args(argv)
    if not args.list_properties and not args.out:
        ap.error("--out を指定してください")
    client = Beds24Client(load_key(args.key_file), log=lambda msg: print(msg, file=sys.stderr))
    return run(args, client)


def run(args, client):
    try:
        kind = client.authenticate()
        print(f"認証OK（{'長期トークン' if kind == 'token' else 'リフレッシュトークン'}）"
              f" scopes: {', '.join(client.scopes()) or '不明'}", file=sys.stderr)
        properties = client.properties()
        if args.list_properties:
            print_properties(properties)
            return 0
        return fetch(client, properties, args)
    except Beds24Error as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1


def fetch(client, properties, args):
    selection = select_rooms(properties, args.name_contains, args.property_id, args.room_id)
    if not selection:
        print("条件に合う施設・部屋がありません。--list-properties で名前とIDを確認してください。", file=sys.stderr)
        return 1
    today = datetime.now(JST).date()
    since_date = datetime.strptime(args.since, "%Y-%m-%d").date() if args.since else today - timedelta(days=args.days)
    until_date = datetime.strptime(args.until, "%Y-%m-%d").date() if args.until else today
    since = datetime.combine(since_date, time.min, JST)
    until = datetime.combine(until_date + timedelta(days=1), time.min, JST)
    departure_from = (since_date - timedelta(days=args.departure_buffer_days)).isoformat()

    selected_props = [p for p in properties if p.get("id") in selection]
    print(f"対象: {', '.join(p.get('name', str(p.get('id'))) for p in selected_props)}", file=sys.stderr)
    print(f"期間: {since_date} 〜 {until_date}（JST）", file=sys.stderr)

    bookings = [b for b in client.bookings(property_ids=sorted(selection), departure_from=departure_from)
                if in_selection(selection, b)]
    print(f"予約 {len(bookings)} 件（{departure_from} 以降に退室）", file=sys.stderr)
    messages = client.messages_for_bookings([b["id"] for b in bookings])

    if args.scan_max_age:
        known = {b["id"] for b in bookings}
        now = datetime.now(JST)
        recent = client.recent_messages((now - since).total_seconds())
        unknown_ids = sorted({m.get("bookingId") for m in recent} - known - {None})
        extra = []
        for i in range(0, len(unknown_ids), 25):
            extra.extend(client.bookings(booking_ids=unknown_ids[i:i + 25], statuses=ALL_BOOKING_STATUSES))
        extra = [b for b in extra if in_selection(selection, b)]
        extra_ids = {b["id"] for b in extra}
        bookings.extend(extra)
        messages.extend(m for m in recent if m.get("bookingId") in extra_ids)
        print(f"maxAge スキャンで追加の予約 {len(extra)} 件", file=sys.stderr)

    unique = {}
    for m in messages:
        t = parse_time(m.get("time"))
        if t is not None and since <= t < until:
            unique[m.get("id")] = slim_message(m)
    messages = list(unique.values())
    booking_ids_with_messages = {m.get("bookingId") for m in messages}
    bookings = [slim_booking(b) for b in {b["id"]: b for b in bookings}.values()
                if b["id"] in booking_ids_with_messages]

    os.makedirs(args.out, exist_ok=True)
    run_info = {
        "fetchedAt": datetime.now(JST).isoformat(timespec="seconds"),
        "since": since_date.isoformat(), "until": until_date.isoformat(),
        "departureFrom": departure_from, "scanMaxAge": args.scan_max_age,
        "selection": {str(pid): (sorted(rooms) if rooms else "all") for pid, rooms in selection.items()},
        "counts": {"bookingsWithMessages": len(bookings), "messages": len(messages)},
        "scopes": client.scopes(),
    }
    save_dataset(args.out, selected_props, bookings, messages, run_info)
    threads = build_threads(selected_props, bookings, messages)
    write_threads_md(os.path.join(args.out, "threads.md"), threads,
                     f"Beds24 メッセージ {since_date} 〜 {until_date}（JST）")
    write_messages_csv(os.path.join(args.out, "messages.csv"), threads)
    print(f"メッセージ {len(messages)} 件 / スレッド {len(threads)} 件を {args.out} に保存しました", file=sys.stderr)
    return 0


def select_rooms(properties, name_contains, property_ids, room_ids):
    """{施設ID: 部屋IDの集合（None なら全部屋）} を返す。条件が無ければ全施設。"""
    if not (name_contains or property_ids or room_ids):
        return {p.get("id"): None for p in properties}
    words = [w.lower() for w in name_contains]
    selection = {}
    for p in properties:
        pid = p.get("id")
        if pid in property_ids or any(w in (p.get("name") or "").lower() for w in words):
            selection[pid] = None
            continue
        rooms = {r.get("id") for r in rooms_of(p)
                 if r.get("id") in room_ids or any(w in (r.get("name") or "").lower() for w in words)}
        if rooms:
            selection[pid] = rooms
    return selection


def in_selection(selection, booking):
    pid = booking.get("propertyId")
    if pid not in selection:
        return False
    rooms = selection[pid]
    return rooms is None or booking.get("roomId") in rooms


def print_properties(properties):
    for p in properties:
        print(f"施設 {p.get('id')}: {p.get('name')}")
        for r in rooms_of(p):
            print(f"    部屋 {r.get('id')}: {r.get('name')}（{r.get('qty', '?')}室）")


def load_key(key_file):
    if key_file:
        with open(key_file, encoding="utf-8") as f:
            return f.read().strip()
    if os.environ.get("BEDS24_TOKEN"):
        return os.environ["BEDS24_TOKEN"].strip()
    if os.path.exists(".beds24_token"):
        with open(".beds24_token", encoding="utf-8") as f:
            return f.read().strip()
    sys.exit("APIキーがありません。環境変数 BEDS24_TOKEN、--key-file、または ./.beds24_token で指定してください。")


if __name__ == "__main__":
    sys.exit(main())

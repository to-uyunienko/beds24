#!/usr/bin/env python3
"""取得したメッセージを施設情報シートの列ごとに仕分け、シートの現在の記載と並べたレビュー資料を作る。

使い方:
  python3 build_review.py --data out/sample --sheet 施設情報.csv --company サンプル管理

出力（--data 配下）:
  review.md     項目別に「シートの記載」と「ゲストの質問＋スタッフの回答」を並べた資料
  qa_pairs.csv  質問1件ごとの一覧（項目・部屋・質問・回答）
"""
import argparse
import csv
import os
import re
import sys
from collections import OrderedDict

from beds24_tools.dataset import build_threads, fmt_jst, guess_lang, load_dataset, parse_time
from beds24_tools.topics import TOPICS, classify

Q_LIMIT, A_LIMIT, SHEET_LIMIT = 600, 900, 1500


def main(argv=None):
    sys.stderr.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="fetch_messages.py の出力フォルダ")
    ap.add_argument("--sheet", help="施設情報シートの CSV（1行目が列名）")
    ap.add_argument("--company", help="シートの「管理会社」列でこの値の行だけを使う")
    ap.add_argument("--title", help="資料のタイトル")
    args = ap.parse_args(argv)

    properties, bookings, messages = load_dataset(args.data)
    threads = build_threads(properties, bookings, messages)
    header, sheet_rows = load_sheet(args.sheet, args.company) if args.sheet else ([], [])
    pairs = extract_pairs(threads, sheet_rows)

    title = args.title or f"施設情報レビュー資料{'：' + args.company if args.company else ''}"
    md = render(title, threads, pairs, header, sheet_rows)
    with open(os.path.join(args.data, "review.md"), "w", encoding="utf-8") as f:
        f.write(md)
    write_pairs_csv(os.path.join(args.data, "qa_pairs.csv"), pairs)
    print(f"{args.data}/review.md と qa_pairs.csv を作成しました（ゲストの質問 {len(pairs)} 件）", file=sys.stderr)
    return 0


# ---- シート ----

def load_sheet(path, company):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    header = rows[0]
    records = [dict(zip(header, r)) for r in rows[1:] if any(c.strip() for c in r)]
    if company:
        records = [r for r in records if r.get("管理会社", "").strip() == company]
    return header, records


def room_numbers(text):
    return re.findall(r"(?<!\d)(\d{3,4})(?!\d)", text or "")


def match_sheet_row(room_label, sheet_rows):
    """Beds24 の施設名/部屋名に含まれる部屋番号でシートの行を探す。1行しか無ければその行。"""
    if len(sheet_rows) == 1:
        return sheet_rows[0]
    nums = set(room_numbers(room_label))
    for r in sheet_rows:
        if nums & set(room_numbers(r.get("施設名", ""))):
            return r
    return None


def sheet_value_summary(sheet_rows, column):
    """列の値を「全室共通」か「部屋ごと」にまとめる。[(対象, 値)] を返す。"""
    values = OrderedDict()
    for r in sheet_rows:
        values.setdefault(r.get(column, "").strip(), []).append(r.get("ID") or r.get("施設名", "?"))
    if len(values) == 1:
        return [("全室共通", next(iter(values)))]
    return [(", ".join(ids), v) for v, ids in values.items()]


# ---- 質問と回答の抽出 ----

def extract_pairs(threads, sheet_rows):
    """ゲストのメッセージ1件ごとに、次のゲスト発言までのホスト回答・内部メモを「回答」として組にする。"""
    pairs = []
    for t in threads:
        msgs = t["messages"]
        row = match_sheet_row(t["room"], sheet_rows) if sheet_rows else None
        for i, m in enumerate(msgs):
            if m.get("source") != "guest":
                continue
            answers = []
            for n in msgs[i + 1:]:
                if n.get("source") == "guest":
                    break
                if n.get("source") in ("host", "internalNote"):
                    answers.append((n.get("source"), (n.get("message") or "").strip(),
                                    fmt_jst(parse_time(n.get("time")))[5:]))
            text = (m.get("message") or "").strip()
            pairs.append({
                "time": fmt_jst(parse_time(m.get("time"))),
                "room": t["room"],
                "sheetId": (row or {}).get("ID", ""),
                "bookingId": t["booking"].get("id"),
                "channel": t["channel"],
                "stay": f"{t['booking'].get('arrival', '?')}→{t['booking'].get('departure', '?')}",
                "lang": guess_lang(text),
                "question": text,
                "answers": answers,
                "topics": classify(text),
            })
    return pairs


# ---- 出力 ----

def render(title, threads, pairs, header, sheet_rows):
    by_topic = OrderedDict((label, []) for label, _c, _p in TOPICS)
    unmatched = []
    for p in pairs:
        for label in p["topics"]:
            by_topic[label].append(p)
        if not p["topics"]:
            unmatched.append(p)

    msg_count = sum(len(t["messages"]) for t in threads)
    period = [p["time"] for p in pairs]
    lines = [f"# {title}", ""]
    lines.append(f"- スレッド（予約）数: {len(threads)} / メッセージ数: {msg_count} / うちゲストのメッセージ: {len(pairs)}")
    if period:
        lines.append(f"- ゲストのメッセージの期間: {min(period)} 〜 {max(period)}（JST）")
    if sheet_rows:
        lines.append(f"- 照合したシートの行: {', '.join(r.get('ID', '') + ' ' + r.get('施設名', '') for r in sheet_rows)}")
    lines += ["", "項目の振り分けはキーワードによる一次仕分けです。1件が複数項目に入ることがあります。", ""]

    lines += ["## 1. 項目別の質問件数", "", "| 項目 | シートの列 | 質問件数 | 予約数 | シートの記載 |", "|---|---|---|---|---|"]
    ranked = sorted(((label, cols, by_topic[label]) for label, cols, _p in TOPICS if by_topic[label]),
                    key=lambda x: -len(x[2]))
    for label, cols, items in ranked:
        lines.append(f"| {label} | {' / '.join(cols) or '（列なし）'} | {len(items)} | "
                     f"{len({p['bookingId'] for p in items})} | {sheet_status(sheet_rows, cols)} |")
    lines.append(f"| （どの項目にも当たらない） | - | {len(unmatched)} | {len({p['bookingId'] for p in unmatched})} | - |")
    lines.append("")

    if sheet_rows:
        lines += ["## 2. シートの空欄・要確認セル", ""]
        skip = {"施設名", "ID", "管理会社"}
        empty = [c for c in header if c not in skip and all(not r.get(c, "").strip() for r in sheet_rows)]
        flagged = [c for c in header if any("⚠" in r.get(c, "") for r in sheet_rows)]
        differs = [c for c in header if c not in skip and len({r.get(c, "").strip() for r in sheet_rows}) > 1]
        asked = {c for label, cols, _p in TOPICS if by_topic[label] for c in cols}
        lines.append(f"- 全室で空欄の列: {', '.join(empty) or 'なし'}")
        lines.append(f"- うち、この期間に実際に質問があった列: {', '.join(c for c in empty if c in asked) or 'なし'}")
        lines.append(f"- 「⚠️」（オーナー確認など）を含む列: {', '.join(flagged) or 'なし'}")
        lines.append(f"- 部屋によって内容が違う列: {', '.join(differs) or 'なし'}")
        lines.append("")

    lines += ["## 3. 項目別の詳細（シートの記載 と 実際のやり取り）", ""]
    for label, cols, items in ranked:
        lines.append(f"### {label}（{len(items)}件）")
        lines.append("")
        if sheet_rows:
            # 同じ内容の列（例: 荷物預けの IN前/OUT後）は1回だけ表示する
            shown = OrderedDict()
            for col in cols:
                shown.setdefault(tuple(sheet_value_summary(sheet_rows, col)), []).append(col)
            for summary, same_cols in shown.items():
                for target, value in summary:
                    lines.append(f"**シートの記載「{'」「'.join(same_cols)}」（{target}）**")
                    lines.append("")
                    lines.append(quote(value, SHEET_LIMIT) if value else "> （空欄）")
                    lines.append("")
        if not cols:
            lines += ["**シートに該当する列がありません（新しい列・FAQ の候補）**", ""]
        lines += render_pairs(items)

    lines += ["## 4. どの項目にも当たらなかったゲストのメッセージ", "",
              "挨拶・お礼が中心ですが、シートに無い質問が混ざっていないか確認してください。", ""]
    lines += render_pairs(unmatched)

    lines += ["## 5. ホストが繰り返し送っている定型メッセージ", "",
              "自動送信・テンプレートの本文です。シートに無い施設情報（入室方法・Wi-Fi など）の出典として確認してください。", ""]
    for text, count in repeated_host_messages(threads):
        lines.append(f"#### {count}回送信")
        lines.append("")
        lines.append(quote(text, 4000))
        lines.append("")
    return "\n".join(lines)


def render_pairs(items):
    lines = []
    for n, p in enumerate(items, 1):
        where = f"{p['room']}{' (' + p['sheetId'] + ')' if p['sheetId'] else ''}"
        lines.append(f"{n}. {p['time']} | {where} | 予約#{p['bookingId']} | {p['channel'] or '-'} | {p['stay']} | {p['lang']}")
        lines.append(f"    - **Q**: {one_line(p['question'], Q_LIMIT)}")
        if p["answers"]:
            for source, text, when in p["answers"]:
                lines.append(f"    - **{'A' if source == 'host' else 'メモ'}**（{when}）: {one_line(text, A_LIMIT)}")
        else:
            lines.append("    - **A**: （この後にホストの返信なし）")
    lines.append("")
    return lines


def repeated_host_messages(threads, min_count=2):
    """先頭の文面が同じホスト/システム送信をまとめ、回数の多い順に (最新の本文, 回数) を返す。"""
    groups = {}
    for t in threads:
        for m in t["messages"]:
            if m.get("source") not in ("host", "system"):
                continue
            text = (m.get("message") or "").strip()
            key = re.sub(r"[\d\s]+", "", text)[:60]
            if len(key) < 20:
                continue
            count, _latest = groups.get(key, (0, ""))
            groups[key] = (count + 1, text)
    return sorted(((text, count) for count, text in groups.values() if count >= min_count), key=lambda x: -x[1])


def sheet_status(sheet_rows, cols):
    if not cols:
        return "列なし"
    if not sheet_rows:
        return "-"
    values = [r.get(c, "") for r in sheet_rows for c in cols]
    if all(not v.strip() for v in values):
        return "**空欄**"
    if any("⚠" in v for v in values):
        return "あり（⚠️要確認を含む）"
    return "あり"


def write_pairs_csv(path, pairs):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["日時(JST)", "項目", "部屋", "シートID", "予約ID", "チャネル", "滞在", "言語", "ゲストの質問", "ホストの回答", "内部メモ"])
        for p in pairs:
            w.writerow([p["time"], " / ".join(p["topics"]) or "（該当なし）", p["room"], p["sheetId"], p["bookingId"],
                        p["channel"], p["stay"], p["lang"], p["question"],
                        "\n---\n".join(t for s, t, _w in p["answers"] if s == "host"),
                        "\n---\n".join(t for s, t, _w in p["answers"] if s == "internalNote")])


def one_line(text, limit):
    text = re.sub(r"\s*\n\s*", " ⏎ ", text or "").strip()
    return text if len(text) <= limit else text[:limit] + " …（省略）"


def quote(text, limit):
    text = text if len(text) <= limit else text[:limit] + "\n…（省略）"
    return "\n".join("> " + line for line in text.splitlines())


if __name__ == "__main__":
    sys.exit(main())

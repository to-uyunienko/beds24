"""シート外ナレッジ（Q&A・手順・前例・注意点など）の列定義、チェック、蓄積用DBへのマージ。

メッセージを読んで抽出するのは人（または Claude）。ここでは書式の確認と、前回までの DB への
追記・更新（ID 採番、根拠の重複除去、初出・最終確認日の管理）だけを機械的に行う。
"""
import csv
import re
from datetime import date, timedelta

COLUMNS = ["ID", "施設", "部屋", "分類", "種類", "項目", "内容", "返信文案", "状態", "重要度",
           "シート反映", "件数", "根拠", "初出", "最終確認", "備考"]

CATEGORIES = ["入室・鍵", "本人確認・名簿", "入国手続き", "予約・人数変更", "料金・支払い", "キャンセル・返金",
              "チェックイン・アウト", "荷物", "設備・使い方", "トラブル対応", "清掃・備品", "寝具", "ゴミ",
              "騒音・近隣", "喫煙", "周辺・観光", "交通・アクセス", "連絡手段", "安全・防災", "部屋・掲載情報",
              "定型文・案内文", "その他"]
KINDS = ["施設情報", "Q&A", "手順", "前例", "注意点", "改善"]
STATES = ["確定", "1件のみ", "回答が割れている", "要オーナー確認"]
IMPORTANCE = ["高", "中", "低"]
REQUIRED = ["施設", "分類", "種類", "項目", "内容", "状態", "重要度"]
CHOICES = {"分類": CATEGORIES, "種類": KINDS, "状態": STATES, "重要度": IMPORTANCE}
# 内容が変わったら備考に前の内容を残す列
TRACKED = ["部屋", "分類", "種類", "項目", "内容", "返信文案", "状態", "重要度", "シート反映"]

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_BOOKING_ID = re.compile(r"#\d+")


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [{c: (row.get(c) or "").strip() for c in COLUMNS} for row in csv.DictReader(f)]


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for row in rows:
            w.writerow({c: row.get(c, "") for c in COLUMNS})


def check(rows):
    """(エラーのリスト, 注意のリスト) を返す。エラーがあればマージしない。"""
    errors, warnings = [], []
    for n, row in enumerate(rows, 2):  # 1行目は見出し
        where = f"{n}行目（{row.get('項目') or '項目なし'}）"
        for col in REQUIRED:
            if not row.get(col):
                errors.append(f"{where}: 「{col}」が空です")
        for col, allowed in CHOICES.items():
            if row.get(col) and row[col] not in allowed:
                errors.append(f"{where}: 「{col}」の「{row[col]}」は使えません（{'／'.join(allowed)}）")
        for col in ("初出", "最終確認"):
            if row.get(col) and not _is_date(row[col]):
                errors.append(f"{where}: 「{col}」は YYYY-MM-DD で書いてください")
        if any(_EMAIL.search(row.get(col, "")) for col in ("内容", "返信文案", "備考")):
            warnings.append(f"{where}: メールアドレスが含まれています。ゲストの個人情報でないか確認してください")
    return errors, warnings


def merge(db_rows, new_rows, today=None):
    """new_rows を db_rows に取り込む。ID が空の行は新規（ID を採番）、既存 ID の行は更新。

    戻り値: (マージ後の行, {"added": [...], "updated": [(行, 変わった列)], "confirmed": [...], "unknown": [ID]})
    """
    today = today or date.today().isoformat()
    db_rows = [dict(r) for r in db_rows]
    by_id = {r["ID"]: r for r in db_rows if r.get("ID")}
    next_no = max((int(m.group(1)) for r in db_rows if (m := re.fullmatch(r"K(\d+)", r.get("ID", "")))), default=0) + 1
    result = {"added": [], "updated": [], "confirmed": [], "unknown": []}
    for new in new_rows:
        if not new.get("ID"):
            row = {c: new.get(c, "") for c in COLUMNS}
            row["ID"] = f"K{next_no:04d}"
            next_no += 1
            row["初出"] = row["初出"] or today
            row["最終確認"] = row["最終確認"] or today
            row["件数"] = _count(row["根拠"], row["件数"])
            db_rows.append(row)
            by_id[row["ID"]] = row
            result["added"].append(row)
            continue
        old = by_id.get(new["ID"])
        if old is None:
            result["unknown"].append(new["ID"])
            continue
        changed = [c for c in TRACKED if new.get(c) and new[c] != old.get(c, "")]
        if changed:
            history = "、".join(f"{c}「{old.get(c, '')}」" for c in changed if old.get(c))
            if history:
                old["備考"] = "\n".join(x for x in (old.get("備考", ""), f"{today} 更新前: {history}") if x)
            for c in changed:
                old[c] = new[c]
        old["根拠"] = _join_unique(old.get("根拠", ""), new.get("根拠", ""))
        old["件数"] = _count(old["根拠"], max(_to_int(old.get("件数")), _to_int(new.get("件数"))))
        old["最終確認"] = max(old.get("最終確認", ""), new.get("最終確認") or today)
        if changed:
            result["updated"].append((old, changed))
        else:
            result["confirmed"].append(old)
    return db_rows, result


def stale(rows, today=None, days=180):
    """最終確認から days 日以上たった行（情報が古くなっていないか確認したいもの）。"""
    limit = (date.fromisoformat(today) if today else date.today()) - timedelta(days=days)
    return [r for r in rows if _is_date(r.get("最終確認", "")) and date.fromisoformat(r["最終確認"]) < limit]


def _count(evidence, fallback):
    """件数は根拠に書かれた予約ID（#数字）の数。予約IDが無い根拠（定型文など）のときは fallback。"""
    ids = set(_BOOKING_ID.findall(evidence or ""))
    return str(len(ids)) if ids else str(_to_int(fallback) or "")


def _join_unique(*texts):
    seen = []
    for text in texts:
        for part in re.split(r"[、\n]", text or ""):
            part = part.strip()
            if part and part not in seen:
                seen.append(part)
    return "、".join(seen)


def _to_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _is_date(text):
    try:
        date.fromisoformat(text)
        return True
    except (TypeError, ValueError):
        return False

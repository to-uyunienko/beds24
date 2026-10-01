#!/usr/bin/env python3
"""シート外ナレッジ（knowledge.csv）を確認し、蓄積用のナレッジDBに追記・更新する。

使い方:
  python3 merge_knowledge.py --template knowledge.csv          # 列見出しだけの空ファイルを作る
  python3 merge_knowledge.py --check knowledge.csv             # 書式チェックだけ
  python3 merge_knowledge.py --new knowledge.csv --db knowledge_db.csv
      # DB に取り込む（DB が無ければ新規作成）。ID が空の行は新規、既存の ID を書いた行は更新
  python3 merge_knowledge.py --db knowledge_db.csv --export "施設名" --out 施設名.csv
      # 1施設分（と「共通」）だけ書き出す

列の意味と書き方は .claude/skills/facility-knowledge/SKILL.md を参照。
DB には暗証番号などが入り得るので、公開リポジトリにはコミットしないこと。
"""
import argparse
import os
import sys
from datetime import date

from beds24_tools.knowledge import COLUMNS, check, merge, read_csv, stale, write_csv


def main(argv=None):
    sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--template", help="列見出しだけの空のナレッジCSVを作る")
    ap.add_argument("--check", help="ナレッジCSVの書式をチェックする")
    ap.add_argument("--new", help="今回抽出したナレッジCSV")
    ap.add_argument("--db", help="蓄積用のナレッジDB（CSV）")
    ap.add_argument("--out", help="書き出し先（既定: --db と同じファイル）")
    ap.add_argument("--export", help="この施設名（と「共通」）の行だけを --out に書き出す")
    ap.add_argument("--date", default=date.today().isoformat(), help="今回の確認日（既定: 今日）")
    ap.add_argument("--stale-days", type=int, default=180, help="最終確認からこの日数を過ぎた行を「要再確認」として表示")
    args = ap.parse_args(argv)

    if args.template:
        write_csv(args.template, [])
        print(f"{args.template} を作成しました（列: {'、'.join(COLUMNS)}）")
        return 0
    if args.check:
        return 0 if report_check(read_csv(args.check)) else 1
    if args.export:
        if not (args.db and args.out):
            ap.error("--export には --db と --out が必要です")
        rows = [r for r in read_csv(args.db) if r["施設"] in (args.export, "共通")]
        write_csv(args.out, rows)
        print(f"{args.out} に {len(rows)} 行を書き出しました")
        return 0
    if not (args.new and args.db):
        ap.error("--template / --check / --export のどれか、または --new と --db を指定してください")

    new_rows = read_csv(args.new)
    if not report_check(new_rows):
        print("エラーがあるため DB は更新していません")
        return 1
    db_rows = read_csv(args.db) if os.path.exists(args.db) else []
    merged, result = merge(db_rows, new_rows, args.date)
    if result["unknown"]:
        print(f"DB に無い ID があります: {'、'.join(result['unknown'])}（ID を空にすると新規として追加されます）")
        return 1
    out = args.out or args.db
    write_csv(out, merged)
    summary = summarize(result, stale(merged, args.date, args.stale_days), args.date)
    with open(os.path.splitext(out)[0] + "_changes.md", "w", encoding="utf-8") as f:
        f.write(summary)
    print(summary)
    print(f"{out}（全 {len(merged)} 行）を保存しました")
    return 0


def report_check(rows):
    errors, warnings = check(rows)
    for msg in errors:
        print(f"エラー: {msg}")
    for msg in warnings:
        print(f"注意: {msg}")
    if not errors:
        print(f"書式OK（{len(rows)} 行）")
    return not errors


def summarize(result, old_rows, today):
    lines = [f"# ナレッジDBの更新（{today}）", "",
             f"- 追加: {len(result['added'])} 件", f"- 内容を更新: {len(result['updated'])} 件",
             f"- 再確認のみ（変更なし）: {len(result['confirmed'])} 件", ""]
    if result["added"]:
        lines += ["## 追加", ""] + [f"- {r['ID']} [{r['施設']}] {r['分類']}｜{r['項目']}（{r['状態']}）" for r in result["added"]] + [""]
    if result["updated"]:
        lines += ["## 更新", ""] + [f"- {r['ID']} [{r['施設']}] {r['項目']}：{'、'.join(cols)} を更新" for r, cols in result["updated"]] + [""]
    if old_rows:
        lines += ["## 長く確認されていない項目（情報が古くなっていないか確認）", ""]
        lines += [f"- {r['ID']} [{r['施設']}] {r['項目']}（最終確認 {r['最終確認']}）" for r in old_rows] + [""]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())

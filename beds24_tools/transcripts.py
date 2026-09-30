"""人が読むための会話ログ。ホストが何度も送る定型文（自動送信など）は T番号に置き換えて短くする。"""
import collections
import html
import os
import re

from beds24_tools.dataset import fmt_jst, parse_time

LABELS = {"guest": "G", "host": "H", "internalNote": "メモ", "system": "S"}


def plain(text):
    """Airbnb の画像リンクなどの HTML を外して素のテキストにする。"""
    text = re.sub(r'<a href="[^"]+"[^>]*>.*?</a>', "[画像/リンク]", text or "", flags=re.S)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).replace("\r\n", "\n").strip()


def _key(text):
    # 宛名の日付や部屋番号が違うだけの文面を同じ定型文として扱う
    return re.sub(r"[\d\s]+", "", plain(text))[:80]


def find_templates(threads, min_count=3):
    """ホスト/システムが min_count 回以上送った文面を探し、[(番号, 送信メッセージのリスト)] を多い順に返す。"""
    groups = collections.defaultdict(list)
    for t in threads:
        for m in t["messages"]:
            key = _key(m.get("message"))
            if m.get("source") in ("host", "system") and len(key) >= 15:
                groups[key].append((t, m))
    ranked = sorted((v for v in groups.values() if len(v) >= min_count), key=len, reverse=True)
    return [(n, sent) for n, sent in enumerate(ranked, 1)]


def write_templates_md(path, templates):
    lines = ["# ホストの定型文（自動送信・テンプレート）", "",
             "施設情報の出典として確認してください。部屋番号などが違うだけの文面は1つにまとめ、最新の本文を載せています。", ""]
    for n, sent in templates:
        props = collections.Counter(t["room"].split(" / ")[0] for t, _m in sent)
        latest = max(sent, key=lambda tm: tm[1].get("time") or "")[1]
        lines.append(f"## T{n}（{len(sent)}回: {', '.join(f'{p} {c}' for p, c in props.most_common())}）")
        lines += ["", plain(latest.get("message")), ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_conversations_md(out_dir, threads, templates):
    """ゲストの発言があるスレッドだけを施設ごとのファイルに書き出す。作成したファイル名のリストを返す。"""
    template_of = {id(m): n for n, sent in templates for _t, m in sent}
    by_property = collections.defaultdict(list)
    for t in threads:
        if any(m.get("source") == "guest" for m in t["messages"]):
            by_property[t["room"].split(" / ")[0]].append(t)
    written = []
    for prop, ts in by_property.items():
        name = "conversations_" + re.sub(r"\W+", "_", prop).strip("_") + ".md"
        lines = [f"# {prop}: ゲストとのやり取り（定型文は templates.md の T番号で省略）", "", f"スレッド数: {len(ts)}", ""]
        for t in ts:
            b = t["booking"]
            lines.append(f"## {t['room']} | #{b.get('id')} | {t['channel'] or '-'} | {b.get('arrival', '?')}→{b.get('departure', '?')}"
                         f" | 大人{b.get('numAdult', '?')} 子{b.get('numChild', '?')} | {b.get('status', '?')}")
            for m in t["messages"]:
                when = fmt_jst(parse_time(m.get("time")))[5:]
                who = LABELS.get(m.get("source"), m.get("source") or "?")
                if id(m) in template_of:
                    lines.append(f"- {when} {who}: [T{template_of[id(m)]}]")
                else:
                    lines.append(f"- {when} {who}: {plain(m.get('message')).replace(chr(10), ' ⏎ ')}")
            lines.append("")
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        written.append(name)
    return written

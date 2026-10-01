import os
import tempfile
import unittest

import merge_knowledge
from beds24_tools.knowledge import check, merge, read_csv, stale, write_csv


def row(**kw):
    base = {"施設": "Sample House", "分類": "荷物", "種類": "Q&A", "項目": "連泊の合間の荷物預かり",
            "内容": "1個1日500円", "状態": "1件のみ", "重要度": "中", "根拠": "#100（9/26）"}
    base.update(kw)
    return base


class KnowledgeTest(unittest.TestCase):
    def test_check_rejects_unknown_choices_and_missing_fields(self):
        errors, warnings = check([row(分類="なんでも"), row(内容=""), row(返信文案="mail me at a@b.co")])
        self.assertTrue(any("分類" in e for e in errors))
        self.assertTrue(any("「内容」が空" in e for e in errors))
        self.assertEqual(len(warnings), 1)

    def test_new_rows_get_ids_dates_and_counts(self):
        merged, result = merge([], [row(), row(項目="傘の貸し出し", 根拠="#1、#2、#2")], "2026-10-01")
        self.assertEqual([r["ID"] for r in merged], ["K0001", "K0002"])
        self.assertEqual(merged[0]["初出"], "2026-10-01")
        self.assertEqual(merged[1]["件数"], "2")
        self.assertEqual(len(result["added"]), 2)

    def test_existing_id_updates_and_keeps_history(self):
        db, _ = merge([], [row()], "2026-10-01")
        db, result = merge(db, [row(ID="K0001", 内容="1個1日700円", 根拠="#100（9/26）、#200（10/20）")], "2026-11-01")
        item = db[0]
        self.assertEqual(item["内容"], "1個1日700円")
        self.assertIn("2026-11-01 更新前: 内容「1個1日500円」", item["備考"])
        self.assertEqual(item["根拠"], "#100（9/26）、#200（10/20）")
        self.assertEqual(item["件数"], "2")
        self.assertEqual(item["最終確認"], "2026-11-01")
        self.assertEqual(item["初出"], "2026-10-01")
        self.assertEqual(result["updated"][0][1], ["内容"])

    def test_same_row_again_is_only_reconfirmed(self):
        db, _ = merge([], [row()], "2026-10-01")
        db, result = merge(db, [row(ID="K0001")], "2026-12-01")
        self.assertEqual(len(result["confirmed"]), 1)
        self.assertEqual(db[0]["件数"], "1")
        self.assertEqual(stale(db, "2027-07-01", 180), db)
        self.assertEqual(stale(db, "2027-01-01", 180), [])

    def test_cli_merges_exports_and_refuses_unknown_ids(self):
        with tempfile.TemporaryDirectory() as d:
            new, db = os.path.join(d, "new.csv"), os.path.join(d, "db.csv")
            write_csv(new, [row(), row(施設="共通", 分類="本人確認・名簿", 項目="パスポートの提出方法")])
            self.assertEqual(merge_knowledge.main(["--new", new, "--db", db, "--date", "2026-10-01"]), 0)
            self.assertEqual(len(read_csv(db)), 2)
            self.assertTrue(os.path.exists(os.path.join(d, "db_changes.md")))
            out = os.path.join(d, "one.csv")
            self.assertEqual(merge_knowledge.main(["--db", db, "--export", "Sample House", "--out", out]), 0)
            self.assertEqual(len(read_csv(out)), 2)  # 施設の行＋共通
            write_csv(new, [row(ID="K0999")])
            self.assertEqual(merge_knowledge.main(["--new", new, "--db", db]), 1)
            self.assertEqual(len(read_csv(db)), 2)


if __name__ == "__main__":
    unittest.main()

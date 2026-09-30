# Beds24 メッセージ → 施設情報シート改善ツール

Beds24 に溜まっているゲストとのメッセージ（Airbnb・Booking.com など）を API で取得し、
施設情報シート（施設早見表）の列ごとに「シートの記載」と「実際の質問・スタッフの回答」を並べた
レビュー資料を作ります。シートの空欄・古い記載・よく聞かれるのに列が無い質問を見つけるためのものです。

Python 3.8 以上の標準ライブラリだけで動きます（追加インストール不要）。

## ⚠️ 取り扱い注意（このリポジトリは公開されています）

- **APIキー、取得したメッセージ（`out/`）、施設情報シートの CSV は絶対にコミットしないでください。**
  `.gitignore` で除外済みです。シートにはキー番号や電話番号、メッセージにはゲストの個人情報が含まれます。
- 予約データは氏名・メール・電話などを除いた項目だけを保存します。メッセージ本文はそのまま保存されます。

## 使い方

### 1. APIキーを設定する

おすすめは **長期トークン（Long life token、読み取り専用）** です。権限（scope）は次の3つを読み取りで付けてください。

- `bookings`（予約）
- `bookings-personal`（メッセージの取得に必要）
- `properties`（施設名・部屋名）

リフレッシュトークンや招待コード（invite code）でも動きます（自動判定）。ただし **Beds24 は交換するたびに新しいキーを発行し、元のキーを無効にします。**
ツールは新しいキーでキーファイルを自動的に上書きするので、キーは必ずファイルで渡し、同時に2つ実行しないでください。

```bash
# キーを書いたファイルを指定する
python3 fetch_messages.py --key-file ~/beds24_token.txt --list-properties
# または、カレントフォルダに .beds24_token というファイルを置く（--key-file 省略時に使われます）
# 長期トークンなら環境変数でも可: export BEDS24_TOKEN='（APIキー）'
```

### 2. 施設・部屋の一覧を確認する

```bash
python3 fetch_messages.py --list-properties
```

### 3. メッセージを取得する（例: 施設名に「Sample House」を含む施設、過去30日）

```bash
python3 fetch_messages.py --name-contains "Sample House" --days 30 --out out/sample
```

- `--name-contains` は施設名・部屋名の部分一致（複数指定可）。`--property-id` / `--room-id` で ID 指定もできます。
  何も指定しなければアカウント内の全施設が対象です。
- `--since 2026-08-30 --until 2026-09-30` で期間を日付指定できます。
- 期間内のメッセージは「期間開始の30日前以降に退室した予約」から集めます（`--departure-buffer-days` で変更可）。
  それより古い予約への連絡も拾いたい場合は `--scan-max-age` を付けます。

出力:

| ファイル | 内容 |
|---|---|
| `threads.md` | 予約ごとの会話ログ（時系列・JST） |
| `messages.csv` | 1メッセージ1行（Excel でそのまま開けます） |
| `raw/*.json` | 取得データ |
| `run_info.json` | 取得条件・件数・トークンの権限 |

### 4. シートと照合したレビュー資料を作る

施設情報シートを CSV で書き出し（1行目が列名）、管理会社名で対象の行を絞ります。

```bash
python3 build_review.py --data out/sample --sheet 施設情報.csv --company サンプル管理
```

| ファイル | 内容 |
|---|---|
| `review.md` | 項目別の質問件数、シートの空欄・⚠️セル、項目ごとの「シートの記載」と「Q&A」、定型メッセージ |
| `qa_pairs.csv` | ゲストの質問1件ごとの一覧（項目・部屋・シートID・質問・回答） |

質問の項目分けは `beds24_tools/topics.py` のキーワード辞書（日本語・英語・中国語・韓国語）による一次仕分けです。
シートの列と対応しない質問は「列なし」として出るので、新しい列や FAQ の候補になります。
部屋とシートの行は、Beds24 の施設名/部屋名とシートの「施設名」に含まれる部屋番号（例: 201）で対応付けます。

## Claude Code（クラウド環境）で実行する場合

環境のネットワーク設定で `beds24.com` と `api.beds24.com` への接続を許可してください。

## テスト

```bash
python3 -m unittest discover -s tests -t .
```

偽の Beds24 API を使ってネットワークなしで取得〜レビュー作成までを確認します。

## API についてのメモ

- Beds24 API V2（`https://api.beds24.com/v2`）の `GET /authentication/details`、`/authentication/token`、
  `/properties`、`/bookings`、`/bookings/messages` を使います（すべて読み取りのみ）。
- 5分あたりのクレジット残量ヘッダー（`x-five-min-limit-remaining`）を見て、少なくなったら自動で待ちます。
- `/bookings/messages` の `maxAge` は公開資料で「秒」とされていますが未検証のため、取得後に必ず日時で絞り込んでいます。

# FANZA データ取得スクリプト — 手順書

## 概要

`scripts/fetch_fanza_works.py` は DMM Web API v3 を使って FANZA 同人作品データを取得し、
`data/works.json` を自動更新するスクリプトです。

---

## APIキー取得手順（一度だけ）

1. [FANZA アフィリエイト](https://affiliate.dmm.com/) でアカウント登録
2. ログイン後、「Web サービス」→「API の利用について」を開く
3. `api_id` と `affiliate_id` を取得する
4. `.env.example` をコピーして `.env` を作成し、取得した値を設定する:

```bash
cp .env.example .env
# .env を編集:
# DMM_API_ID=取得した api_id
# DMM_AFFILIATE_ID=取得した affiliate_id
```

---

## 実行方法

### 通常モード（APIキー設定後）

```bash
# 新着100件を取得して works.json を更新
python3 scripts/fetch_fanza_works.py

# キーワードで絞り込み（作者名・ジャンル等）
python3 scripts/fetch_fanza_works.py --keyword "作者名"

# 最大300件取得
python3 scripts/fetch_fanza_works.py --max-hits 300
```

### ダミーモード（APIキー取得前）

```bash
# --dry-run でダミーデータを使用（APIキー不要）
python3 scripts/fetch_fanza_works.py --dry-run
```

ダミーモードでは `scripts/fanza_api_mock.json` のデータを使って動作確認できます。
実行ログは `/tmp/fanza_dry.log` に保存されます。

---

## DMM API レスポンス → works.json フィールドマッピング

| DMM API フィールド         | works.json フィールド | 変換処理                         |
|---------------------------|----------------------|----------------------------------|
| `content_id`              | `id`                 | そのまま (例: "d_123456")        |
| `title`                   | `title`              | そのまま                         |
| `iteminfo.maker[0].name`  | `author`             | 先頭要素の name                  |
| (author から生成)          | `author_slug`        | slugify 変換 (ASCII ハイフン区切り) |
| `prices.price`            | `price`              | int 変換 (円単位)                |
| `date`                    | `release_date`       | YYYY-MM-DD 形式に正規化          |
| `iteminfo.genre[].name`   | `genres`             | name 配列に変換                  |
| `imageURL.list`           | `thumbnail`          | FANZA 画像直リンク               |
| `affiliateURL`            | `fanza_link`         | アフィリエイト URL               |
| `iteminfo.volume`         | `pages`              | int 変換 (不明時は null)         |
| `review.average`          | `rating`             | float 変換 (なければ null)       |
| (固定値)                  | `review_slug`        | null (レビュー記事は手動管理)    |

---

## works.json スキーマ

```json
{
  "works": [
    {
      "id": "d_123456",
      "title": "作品タイトル",
      "author": "作者名",
      "author_slug": "sakusha-mei",
      "price": 880,
      "release_date": "2026-01-15",
      "genres": ["恋愛", "フルカラー"],
      "thumbnail": "https://pics.dmm.co.jp/...",
      "fanza_link": "https://al.dmm.co.jp/?...",
      "review_slug": null,
      "pages": 32,
      "rating": 4.2
    }
  ]
}
```

---

## 注意事項

- DMM API は RPS 制限あり。スクリプト内で 0.5 秒スリープして律儀に叩いています
- `.env` は `.gitignore` に追加済み（APIキーを git に含めないよう注意）
- 実行前に `data/works.json` が自動バックアップ (`.json.bak`) されます
- `review_slug` は null のまま。レビュー記事を書いた後に手動で設定してください

---

## 将来の拡張（別タスク想定）

- **試し読み画像取得**: DMM API 外のため Playwright 別タスクとして実装予定
- **定期自動更新**: cron で毎日/週次に自動実行
- **新着検知**: 前回取得との差分で新作のみ通知

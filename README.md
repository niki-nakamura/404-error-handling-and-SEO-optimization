以下では、**「GitHubのプライベートリポジトリにPythonスクリプトを配置し、サイトマップからURLを取得→404チェック→Slack通知を定期実行する」** ための、推奨フォルダ構成と具体的なファイル内容をまとめます。  

---

# 推奨フォルダ構成

```
404-error-handling-and-SEO-optimization
├─ .github
│   └─ workflows
│       └─ check_404.yml           # GitHub Actionsの設定ファイル
│       └─ crawl_links.yml
├─ scripts
│   └─ check_404.py                # 実際のスクリプト本体
│   └─ crawl_links.py
├─ README.md               　　　　 # リポジトリ全体の説明書
├─ flow.md
└─ requirements.txt           　　　# Python依存パッケージのリスト      
```

1. **`.github/workflows/check_404.yml`**  
   - GitHub Actionsで定期実行するためのワークフローファイルです。  
2. **`scripts/check_404.py`**  
   - サイトマップを読み取り、URLを抽出して404を検出し、Slackに通知するPythonスクリプト。  
3. **`requirements.txt`**  
   - `requests`など、Pythonスクリプト実行に必要なライブラリを明記します。  
4. **`README.md`**  
   - セットアップ手順や使い方をドキュメント化しておくと、プロジェクトのメンバーや将来の運用で助かります。

---

# ファイル内容

## 1. `.github/workflows/check_404.yml`

### ポイント
- `on.schedule.cron` で毎日午前2時(UTC)に定期実行。日本時間では午前11時になります。  
- `workflow_dispatch` で「Actions」タブから手動実行も可能。  
- `SLACK_WEBHOOK_URL` はGitHubリポジトリの「Settings > Secrets and variables > Actions」から**シークレット変数**として登録してください。

---

## 2. `scripts/check_404.py`

- **トップのサイトマップ**(`https://good-apps.jp/sitemap.xml`)を取得  
- 中に列挙されている**サブサイトマップ**(例えば `sitemap-pt-post-p1-2025-01.xml` など)を再帰的に取得し、そこに含まれる**全URL**を`requests.get()`でチェック  
- ステータスコードが**404**のURLだけをSlackに通知という流れです。

### スクリプトの動作概要
1. **`MAIN_SITEMAP_URL`**（`https://good-apps.jp/sitemap.xml`）を取得。  
2. **`extract_sitemap_urls()`** で「サブサイトマップ」があるか確認し、再帰的にたどる。  
3. **`extract_page_urls()`** で実際の「投稿ページのURL」を抽出。  
4. 全URLに対し**GETリクエスト**を送信し、**`404`のみ抽出**。  
5. Slack Webhookへ結果を通知（検出件数が0なら「404はありません」報告）。

---

## 3. `requirements.txt`

- スクリプトで使うライブラリのバージョンを指定。  
- GitHub Actionsの「Install dependencies」ステップで `pip install -r requirements.txt` が実行されます。

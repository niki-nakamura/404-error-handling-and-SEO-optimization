以下では、**GitHub Actionsを使って週2回（毎週月・木）にサイト全体のリンク切れ(404など)を検出し、Slackに通知する運用フロー**をまとめます。  

---

# 1. 運用フロー概要

1. **リポジトリ準備**  
   - GitHubにプライベートリポジトリを作成する（例: `link-checker`）  
   - Pythonのクローラスクリプト（`crawl_links.py`）や、GitHub Actions用のワークフローファイル（`crawl_links.yml`）を配置

2. **クローラスクリプト**  
   - Pythonでサイトのトップページからリンクを辿り、HTTPステータスをチェックするコードを実装  
   - 404などエラーを検出したらリストアップ

3. **Slack通知**  
   - スクリプトが検出したエラーリンクをまとめ、Slack Webhookを通じて指定のチャンネルに投稿  
   - **Slack Webhook URLはGitHub Secrets**に登録し、プライベートリポジトリで安全に取り扱う

4. **GitHub Actionsで定期実行**  
   - `.github/workflows/`内にワークフローファイルを設置  
   - **CRON設定**で「毎週月曜と木曜の特定時刻（UTCベースでの時間指定）」に自動実行  
   - 成果物としてSlackに404検出結果が投稿される

5. **結果の確認・対応**  
   - Slackの通知を確認し、必要に応じて修正、リダイレクト設定などを実施

---

# GitHub Actionsのワークフローファイル

以下では、**毎週月・木の午前8:00(UTC)に実行**するよう設定しています。（UTC 08:00 は日本時間で17:00）

```yaml
# .github/workflows/crawl_links.yml

name: Link Checker

on:
  schedule:
    # 月曜・木曜の午前8時(UTC)に定期実行
    - cron: '0 8 * * 1'
    - cron: '0 8 * * 4'
  workflow_dispatch:  # 手動トリガー可能

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Check out the repository
        uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.x'

      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run crawler
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
        run: |
          python scripts/crawl_links.py
```

### ポイント

1. `schedule.cron` で定期実行タイミングを設定  
   - `cron: '0 8 * * 1'` → 毎週月曜08:00 UTC  
   - `cron: '0 8 * * 4'` → 毎週木曜08:00 UTC  
2. `workflow_dispatch` を追加しておくと、GitHubのActionsタブから手動で実行可能  
3. **Slack Webhook URL**は、リポジトリの`Settings > Secrets and variables > Actions` で `SLACK_WEBHOOK_URL` という名前で登録

---

# 2. 手順まとめ

1. **GitHubリポジトリ作成**  
   - 例: `link-checker`

2. **ファイルアップロード**  
   - `.github/workflows/crawl_links.yml`  
   - `scripts/crawl_links.py`  
   - `requirements.txt`  
   - `README.md`

3. **Secrets設定**  
   - リポジトリの「Settings > Secrets and variables > Actions」で  
     - キー: `SLACK_WEBHOOK_URL`  
     - 値: `https://hooks.slack.com/services/xxxxx/xxxxx/xxxxx`（Incoming WebhookのURL）

4. **GitHub Actionsを有効化**  
   - `main`ブランチなどにファイルをプッシュ  
   - 「Actions」タブを確認し、「crawl_links」ワークフローが設定されているかチェック

5. **運用開始**  
   - 毎週月曜・木曜の指定時刻に自動実行  
   - Slackにて「リンク切れ報告」が行われる  
   - 404など発生したURLを確認→ 必要に応じて修正・リダイレクト対応

---

## 3. 補足・注意点

- **大規模サイトへの対応**  
  - ページ数が非常に多い場合、巡回に時間がかかる・メモリ使用量が増えるなどが発生し得ます。  
  - 必要に応じて「クロール上限を設定」「並列処理」「特定ディレクトリのみクロール」などの工夫が必要です。  
- **外部リンクの扱い**  
  - サイト内だけチェックしたい場合は、外部リンクはスキップするor404チェックだけする、といった制御を行うと効率的です。  
- **robots.txt** や **サイト運営ポリシー**に従い、意図しないディレクトリまでクロールしないよう注意する場合があります。  

---

# まとめ

- **GitHub Actions + Pythonスクリプト**で、週2回（月曜・木曜）のリンク切れチェックとSlack通知が無料かつ自動で行えます。  
- **ファイル構成**は `.github/workflows/` 以下にワークフローファイル、 `scripts/` にPythonスクリプト、 `requirements.txt` で依存管理という形がおすすめです。  
- **SlackのWebhook URL**をGitHub Secretsに登録すれば、プライベートリポジトリでも安全に運用可能。  

これで**定期的に404エラーやリンク切れを検出し、チームにアラートを出すフロー**を確立できます。

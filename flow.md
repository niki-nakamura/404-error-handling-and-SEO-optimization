以下では、**GitHub Actionsを使って週2回（毎週月・木）にサイト全体のリンク切れ(404など)を検出し、Slackに通知する運用フロー**をまとめます。  
あわせて、**GitHubリポジトリのファイル構造例**や設定手順も示します。

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

# 2. リポジトリ構造例

```
link-checker/
├─ .github/
│   └─ workflows/
│       └─ crawl_links.yml          # GitHub Actionsのワークフロー定義
├─ scripts/
│   └─ crawl_links.py               # Pythonスクリプト本体（クローラーとSlack通知）
├─ requirements.txt                 # Python依存ライブラリ管理
└─ README.md                        # プロジェクトの概要・運用手順
```

### 2-1. 主要ファイルの役割

- **`.github/workflows/crawl_links.yml`**  
  - GitHub Actionsの設定ファイル（定期実行のCRONや依存ライブラリのインストール手順などを記述）

- **`scripts/crawl_links.py`**  
  - クローラー本体  
  - 指定したURLを起点にリンクを辿る  
  - 404などのエラーステータスを検出しSlackへ通知

- **`requirements.txt`**  
  - `requests` や `beautifulsoup4` など、Pythonで必要なパッケージを指定  
  - 例：  
    ```
    requests>=2.0
    beautifulsoup4>=4.0
    ```

- **`README.md`**  
  - セットアップ手順・ローカルでの実行方法・ワークフローの概要などを記載

---

# 3. GitHub Actionsのワークフローファイル例

以下の例では、**毎週月・木の午前8:00(UTC)に実行**するよう設定しています。（UTC 08:00 は日本時間で17:00）

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

# 4. スクリプト例：`scripts/crawl_links.py`

大まかなイメージは次のとおりです。（要件やサイト規模に応じて拡張可能）

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os
from collections import deque

START_URL = "https://good-apps.jp/"  # 開始URL
BASE_DOMAIN = "good-apps.jp"        # ドメインチェックに使用
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

visited = set()
broken_links = []

def is_internal_link(url):
    parsed = urlparse(url)
    return (parsed.netloc == "" or parsed.netloc.endswith(BASE_DOMAIN))

def crawl(start_url):
    queue = deque([start_url])
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        if not is_internal_link(current):
            # 外部リンクの場合はステータスだけ確認
            check_status(current)
            continue

        # 内部リンク: HTML取得 -> リンク解析
        try:
            resp = requests.get(current, timeout=10)
            if resp.status_code >= 400:
                broken_links.append((current, resp.status_code))
                continue

            soup = BeautifulSoup(resp.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                link = urljoin(current, a['href'])
                link = urlparse(link)._replace(fragment="").geturl()
                if link not in visited:
                    queue.append(link)
        except Exception as e:
            broken_links.append((current, f"Error: {str(e)}"))

def check_status(url):
    # 外部リンクの簡易チェック
    try:
        r = requests.head(url, timeout=5)
        if r.status_code >= 400:
            broken_links.append((url, r.status_code))
    except Exception as e:
        broken_links.append((url, f"Error: {str(e)}"))

def send_slack_notification(broken):
    if not SLACK_WEBHOOK_URL:
        print("SLACK_WEBHOOK_URL is not set.")
        return

    if not broken:
        msg = "[Link Checker]\nNo broken links found!"
    else:
        msg = "[Link Checker]\nBroken links found:\n"
        for url, status in broken:
            msg += f"- {url} [Status: {status}]\n"

    try:
        requests.post(SLACK_WEBHOOK_URL, json={"text": msg}, timeout=10)
    except Exception as e:
        print(f"Slack notification failed: {e}")

def main():
    print(f"Starting crawl from {START_URL}")
    crawl(START_URL)
    print("Crawl finished.")
    print(f"Detected {len(broken_links)} broken links.")

    send_slack_notification(broken_links)

if __name__ == "__main__":
    main()
```

---

# 5. 手順まとめ

1. **GitHubリポジトリ作成**  
   - 例: `link-checker` (プライベート/パブリックは任意)

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

## 6. 補足・注意点

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

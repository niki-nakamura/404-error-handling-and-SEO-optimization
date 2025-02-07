以下では、**「GitHubのプライベートリポジトリにPythonスクリプトを配置し、サイトマップからURLを取得→404チェック→Slack通知を定期実行する」** ための、推奨フォルダ構成例と具体的なファイル内容をまとめます。  

---

# 推奨フォルダ構成

```
404-error-handling-and-SEO-optimization
├─ .github
│   └─ workflows
│       └─ check_404.yml            # GitHub Actionsの設定ファイル
├─ scripts
│   └─ check_404.py                 # 実際のスクリプト本体
├─ requirements.txt                 # Python依存パッケージのリスト
└─ README.md                        # リポジトリ全体の説明書
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

# ファイル内容サンプル

## 1. `.github/workflows/check_404.yml`

```yaml
name: Check 404

# スケジュールの設定
# 下記のcronはUTC時刻で "0 2 * * *" = 毎日AM2時 (日本時間で11時) に実行
on:
  schedule:
    - cron: '0 2 * * *'
  workflow_dispatch:  # 手動トリガーでも実行可能にしておく

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - name: Check out the repo
        uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.x'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      - name: Run 404 check script
        # secrets.SLACK_WEBHOOK_URL はGitHubの「Settings > Secrets and variables > Actions」で登録
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
        run: |
          python scripts/check_404.py
```

### ポイント
- `on.schedule.cron` で毎日午前2時(UTC)に定期実行。日本時間では午前11時になります。  
- `workflow_dispatch` で「Actions」タブから手動実行も可能。  
- `SLACK_WEBHOOK_URL` はGitHubリポジトリの「Settings > Secrets and variables > Actions」から**シークレット変数**として登録してください。

---

## 2. `scripts/check_404.py`

以下のPythonスクリプトは、  
- **トップのサイトマップ**(`https://good-apps.jp/sitemap.xml`)を取得  
- 中に列挙されている**サブサイトマップ**(例えば `sitemap-pt-post-p1-2025-01.xml` など)を再帰的に取得し、  
- そこに含まれる**全URL**を`requests.get()`でチェック  
- ステータスコードが**404**のURLだけをSlackに通知  
という流れのサンプルです。

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import xml.etree.ElementTree as ET
import os

# SlackのWebhook URL（GitHub Secretsにて登録し、envで読み込む）
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

# メインサイトマップ
MAIN_SITEMAP_URL = "https://good-apps.jp/sitemap.xml"

def fetch_sitemap(url):
    """
    指定したサイトマップURLを取得し、XMLのルート要素を返す。
    失敗時はNone。
    """
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            root = ET.fromstring(r.text)
            return root
    except Exception as e:
        print(f"[Error] Failed to fetch sitemap: {url} \n {e}")
    return None

def extract_sitemap_urls(sitemap_root):
    """
    ルート要素から <loc> を持つサブサイトマップURLをリストで返す。
    たとえば <sitemap><loc>～</loc></sitemap> のURLが対象。
    """
    urls = []
    if sitemap_root is None:
        return urls
    ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    # サイトマップインデックスの場合は <sitemap> タグ内に <loc> がある
    for sitemap in sitemap_root.findall('ns:sitemap', ns):
        loc = sitemap.find('ns:loc', ns)
        if loc is not None and loc.text:
            urls.append(loc.text.strip())
    return urls

def extract_page_urls(sitemap_root):
    """
    サブサイトマップ（URLリストが直接含まれるもの）から <url><loc>～</loc></url> のURLを取得。
    """
    urls = []
    if sitemap_root is None:
        return urls
    ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    for url_elem in sitemap_root.findall('ns:url', ns):
        loc = url_elem.find('ns:loc', ns)
        if loc is not None and loc.text:
            urls.append(loc.text.strip())
    return urls

def get_all_urls_from_sitemaps(url):
    """
    メインサイトマップ -> サブサイトマップ -> 各URL の階層を再帰的にたどり、
    すべてのURL（最終的にWebページへのリンク）を集めて返す。
    """
    all_urls = []
    root = fetch_sitemap(url)
    if root is None:
        return all_urls

    # サブサイトマップのURL一覧を抜き出す
    subs = extract_sitemap_urls(root)

    if subs:
        # サブサイトマップがある場合、再帰的にたどる
        for sub in subs:
            sub_root = fetch_sitemap(sub)
            # さらにサブサブがあるかもしれない
            deeper_subs = extract_sitemap_urls(sub_root)
            if deeper_subs:
                for deeper_sub in deeper_subs:
                    deeper_root = fetch_sitemap(deeper_sub)
                    all_urls.extend(extract_page_urls(deeper_root))
            else:
                # ここに直接URLが含まれているはず
                all_urls.extend(extract_page_urls(sub_root))
    else:
        # サブサイトマップがない場合、直接URLが含まれている可能性あり
        all_urls.extend(extract_page_urls(root))

    return all_urls

def check_404_urls(url_list):
    """
    GETリクエストして404のURLをリストで返す。
    """
    not_found = []
    for u in url_list:
        try:
            resp = requests.get(u, timeout=10)
            if resp.status_code == 404:
                not_found.append(u)
        except Exception as e:
            # ネットワークエラーやタイムアウトはとりあえず404扱いにはせず、ログだけ残す
            print(f"[Warning] Request error for {u}: {e}")
    return not_found

def send_slack_notification(message):
    """
    Slack Webhookに対してメッセージをPOSTする。
    """
    if not SLACK_WEBHOOK_URL:
        print("[Error] SLACK_WEBHOOK_URL is not set.")
        return

    payload = {"text": message}
    try:
        r = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
        if r.status_code != 200:
            print(f"[Error] Slack responded with status {r.status_code}: {r.text}")
    except Exception as e:
        print(f"[Error] Failed to send Slack notification: {e}")

def main():
    print("[Info] Starting 404 check ...")

    # 1) サイトマップから全URLを抽出
    all_urls = get_all_urls_from_sitemaps(MAIN_SITEMAP_URL)
    print(f"[Info] Found {len(all_urls)} URLs in sitemap(s).")

    # 2) 404のURLをチェック
    not_found_urls = check_404_urls(all_urls)

    # 3) Slack通知
    if not not_found_urls:
        message = "【404チェック結果】\n404は検出されませんでした。"
    else:
        message = "【404チェック結果】\n以下のURLが404でした:\n" + "\n".join(not_found_urls)

    print("[Info] Sending Slack notification...")
    send_slack_notification(message)
    print("[Info] Done.")

if __name__ == "__main__":
    main()
```

### スクリプトの動作概要
1. **`MAIN_SITEMAP_URL`**（`https://good-apps.jp/sitemap.xml`）を取得。  
2. **`extract_sitemap_urls()`** で「サブサイトマップ」があるか確認し、再帰的にたどる。  
3. **`extract_page_urls()`** で実際の「投稿ページのURL」を抽出。  
4. 全URLに対し**GETリクエスト**を送信し、**`404`のみ抽出**。  
5. Slack Webhookへ結果を通知（検出件数が0なら「404はありません」報告）。

---

## 3. `requirements.txt`

```text
requests>=2.0
```

- スクリプトで使うライブラリのバージョンを指定。  
- GitHub Actionsの「Install dependencies」ステップで `pip install -r requirements.txt` が実行されます。

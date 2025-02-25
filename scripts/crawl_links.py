#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os
from collections import deque
import pandas as pd

ALLOWED_SOURCE_PREFIXES = [
    # テスト用に短いドメイン例
    "https://www.example.com/"
]

BASE_DOMAIN = "example.com"  # 内部判定用

MAX_404 = 5   # 404発見数が5件に達したら中断
visited = set()
broken_links = []

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/115.0.0.0 Safari/537.36"
}

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

def is_internal_link(url):
    parsed = urlparse(url)
    return (parsed.netloc == "" or parsed.netloc.endswith(BASE_DOMAIN))

def is_excluded_domain(url):
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    exclude_keywords = [
        "google.com",
        "play.google.com",
        # ...
    ]
    return any(k in domain for k in exclude_keywords)

def is_allowed_source(url):
    return any(url.startswith(prefix) for prefix in ALLOWED_SOURCE_PREFIXES)

def record_broken_link(source, url, status):
    # 404発見数が5件に達したら中断するため、呼び出し元でチェック
    broken_links.append((source, url, status))

def crawl():
    queue = deque(ALLOWED_SOURCE_PREFIXES)
    while queue:
        if len(broken_links) >= MAX_404:
            print(f"[DEBUG] {MAX_404}件の404を検知。クロールを終了します。")
            return

        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        print(f"[DEBUG] Crawling: {current}")
        try:
            resp = requests.get(current, headers=HEADERS, timeout=10)
            print(f"[DEBUG] Fetched {current} - Status: {resp.status_code}")

            # 404でも ALLOWED_SOURCE_PREFIXES のURLなら継続してリンク抽出
            if resp.status_code == 404 and current not in ALLOWED_SOURCE_PREFIXES:
                # 発生元が ALLOWED_SOURCE_PREFIXES に含まれていれば broken_links に追加
                if is_allowed_source(current):
                    record_broken_link(current, current, 404)
                if len(broken_links) >= MAX_404:
                    return
                continue

            soup = BeautifulSoup(resp.text, 'html.parser')
            for a_tag in soup.find_all('a', href=True):
                if len(broken_links) >= MAX_404:
                    return

                link = urljoin(current, a_tag['href'])
                link = urlparse(link)._replace(fragment="").geturl()
                print(f"[DEBUG] Found link: {link}")

                if not is_internal_link(link):
                    if is_excluded_domain(link):
                        continue
                    check_status(link, current)
                    if len(broken_links) >= MAX_404:
                        return
                else:
                    if is_allowed_source(link) and link not in visited:
                        queue.append(link)

        except Exception as e:
            print(f"[DEBUG] Exception while processing {current}: {e}")
            # 404でなくエラーの場合は任意で記録するか決める
            pass

def check_status(url, source):
    try:
        r = requests.head(url, headers=HEADERS, timeout=5, allow_redirects=True)
        if r.status_code == 404:
            record_broken_link(source, url, 404)
        elif r.status_code in (403, 405):
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code == 404:
                record_broken_link(source, url, 404)
    except:
        pass

def update_streamlit_data(broken):
    df = pd.DataFrame(broken, columns=["source", "url", "status"])
    df.to_csv("broken_links.csv", index=False)
    print("[DEBUG] 'broken_links.csv' written.")

def send_slack_notification(broken):
    if not SLACK_WEBHOOK_URL:
        print("No Slack webhook URL set.")
        return

    msg = f"【テスト用404チェック結果】\n404が {len(broken)} 件検出されました。"
    try:
        r = requests.post(SLACK_WEBHOOK_URL, json={"text": msg}, headers=HEADERS, timeout=10)
        if r.status_code not in [200, 204]:
            print(f"[DEBUG] Slack notification failed: {r.status_code}, {r.text}")
    except Exception as e:
        print(f"[DEBUG] Slack notification error: {e}")

def main():
    crawl()
    print(f"[INFO] Detected {len(broken_links)} broken links.")
    update_streamlit_data(broken_links)
    send_slack_notification(broken_links)

if __name__ == "__main__":
    main()

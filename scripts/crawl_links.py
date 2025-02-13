#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os
from collections import deque
import gspread
from google.oauth2.service_account import Credentials

# クロール対象のURLは以下の3つのみ
ALLOWED_SOURCE_PREFIXES = [
    "https://good-apps.jp/media/column/",
    "https://good-apps.jp/media/categor",
    "https://good-apps.jp/media/app"
]

BASE_DOMAIN = "good-apps.jp"  # 内部リンクの判定に使用

# 404エラー検知の上限
ERROR_LIMIT = 10

visited = set()
# broken_links のタプル形式は (発生元記事, 壊れているリンク, ステータス)
broken_links = []

# ブラウザ風の User-Agent を設定
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

# Slack Webhook 用の設定
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
# Google Sheets 用の設定（シートIDのみを指定する）
GOOGLE_SHEET_ID = "1DrEs-tAk2zlqKXBzVIwl2cbo_m7x39ySCKUjg7y_o7I"

def is_internal_link(url):
    """
    URL が内部リンク (good-apps.jp) かどうかを判定
    """
    parsed = urlparse(url)
    return (parsed.netloc == "" or parsed.netloc.endswith(BASE_DOMAIN))

def is_excluded_domain(url):
    """
    Google系ドメインなど、404チェック不要のものはここで除外する
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    exclude_keywords = [
        "google.com",
        "play.google.com",
        "google.co.jp",
        "gstatic.com",
        "g.co",
        "youtu.be",
        "youtube.com",
    ]
    return any(k in domain for k in exclude_keywords)

def is_allowed_source(url):
    """
    発生元記事またはクロール対象として許可されているかを判定
    許可対象は ALLOWED_SOURCE_PREFIXES に含まれるURLのみ
    """
    return any(url.startswith(prefix) for prefix in ALLOWED_SOURCE_PREFIXES)

def record_broken_link(source, url, status):
    """
    発生元記事が許可されている場合のみ、broken_links に追加する
    """
    if source and is_allowed_source(source):
        broken_links.append((source, url, status))

def crawl():
    # 初期キューは許可対象の3つのURL
    queue = deque(ALLOWED_SOURCE_PREFIXES)
    while queue:
        if len(broken_links) >= ERROR_LIMIT:
            print(f"[DEBUG] Error limit of {ERROR_LIMIT} reached. Stopping crawl.")
            return

        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        print(f"[DEBUG] Crawling: {current}")

        try:
            resp = requests.get(current, headers=HEADERS, timeout=10)
            print(f"[DEBUG] Fetched {current} - Status: {resp.status_code}")
            if resp.status_code == 404:
                # 直接アクセスしたページが404の場合、発生元記事として許可されているかチェック
                if is_allowed_source(current):
                    broken_links.append((current, current, resp.status_code))
                if len(broken_links) >= ERROR_LIMIT:
                    print(f"[DEBUG] Error limit reached after processing {current}.")
                    return
                continue

            soup = BeautifulSoup(resp.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                if len(broken_links) >= ERROR_LIMIT:
                    print(f"[DEBUG] Error limit reached during link extraction.")
                    return
                link = urljoin(current, a['href'])
                link = urlparse(link)._replace(fragment="").geturl()
                print(f"[DEBUG] Found link: {link}")

                # 外部リンクの場合
                if not is_internal_link(link):
                    if is_excluded_domain(link):
                        continue
                    # 外部リンクは、現在のページ (current) を発生元としてチェック
                    check_status(link, current)
                    if len(broken_links) >= ERROR_LIMIT:
                        print(f"[DEBUG] Error limit reached during external link check.")
                        return
                else:
                    # 内部リンクは、許可対象（ALLOWED_SOURCE_PREFIXES）に限定してクロール
                    if is_allowed_source(link) and link not in visited:
                        queue.append(link)

        except Exception as e:
            print(f"[DEBUG] Exception while processing {current}: {e}")
            if is_allowed_source(current):
                broken_links.append((current, current, f"Error: {str(e)}"))
            if len(broken_links) >= ERROR_LIMIT:
                print(f"[DEBUG] Error limit reached after exception in {current}.")
                return

def check_status(url, source):
    if is_excluded_domain(url):
        return
    try:
        r = requests.head(url, headers=HEADERS, timeout=5, allow_redirects=True)
        print(f"[DEBUG] Checking URL: {url} - Status: {r.status_code}")
        if r.status_code == 404:
            record_broken_link(source, url, 404)
        elif r.status_code in (403, 405):
            r = requests.get(url, headers=HEADERS, timeout=10)
            print(f"[DEBUG] GET fallback for URL: {url} - Status: {r.status_code}")
            if r.status_code == 404:
                record_broken_link(source, url, 404)
    except Exception as e:
        print(f"[DEBUG] Exception in check_status for URL: {url} - {e}")
        pass

def update_google_sheet(broken):
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file("service_account.json", scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(GOOGLE_SHEET_ID).sheet1

    for source, url, status in broken:
        row = [url, source, status]
        print(f"[DEBUG] Appending row to sheet: {row}")
        sheet.append_row(row)

def send_slack_notification(broken):
    if not SLACK_WEBHOOK_URL:
        print("SLACK_WEBHOOK_URL is not set.")
        return

    count = len(broken)
    sheets_url = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/edit?gid=0"
    msg = (f"【404チェック結果】\n"
           f"404が {count} 件検出されました。\n"
           f"こちらよりエラーURLを確認してください。\n({sheets_url})")

    try:
        r = requests.post(SLACK_WEBHOOK_URL, json={"text": msg}, headers=HEADERS, timeout=10)
        if r.status_code not in [200, 204]:
            print(f"[DEBUG] Slack notification failed with status {r.status_code}: {r.text}")
    except Exception as e:
        print(f"[DEBUG] Slack notification failed: {e}")

def main():
    print("Starting crawl from allowed URLs:")
    for url in ALLOWED_SOURCE_PREFIXES:
        print(f" - {url}")
    crawl()
    print("Crawl finished.")
    print(f"Detected {len(broken_links)} broken links.")
    update_google_sheet(broken_links)
    send_slack_notification(broken_links)

if __name__ == "__main__":
    main()

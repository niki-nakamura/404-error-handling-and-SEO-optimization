#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os
from collections import deque
import gspread
from google.oauth2.service_account import Credentials

# 調査対象のURL（good-apps.jp）
START_URL = "https://good-apps.jp/"
BASE_DOMAIN = "good-apps.jp"  # 内部リンクの判定に使用

visited = set()
# broken_links のタプル形式は (参照元, 壊れているリンク, ステータス) とする
broken_links = []

# 404エラー検知の上限
ERROR_LIMIT = 10

# ブラウザ風の User-Agent を設定
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

# Slack Webhook 用の設定
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
# Google Sheets 用の設定（シートIDのみを指定する）
GOOGLE_SHEET_ID = "1Ht9EjkZebHhm2gA6q5KR16Qs8jppSdaud-QxJZ2y7tU"  # 実際のシートIDに置き換える

def is_internal_link(url):
    parsed = urlparse(url)
    return (parsed.netloc == "" or parsed.netloc.endswith(BASE_DOMAIN))

def crawl(start_url):
    queue = deque([start_url])
    while queue:
        # 既にエラー件数が上限に達している場合は終了
        if len(broken_links) >= ERROR_LIMIT:
            print(f"[DEBUG] Error limit of {ERROR_LIMIT} reached. Stopping crawl.")
            return

        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        print(f"[DEBUG] Crawling: {current}")

        if is_internal_link(current):
            try:
                resp = requests.get(current, headers=HEADERS, timeout=10)
                print(f"[DEBUG] Fetched {current} - Status: {resp.status_code}")
                # 404の場合はエラーとして記録
                if resp.status_code == 404:
                    print(f"[DEBUG] 404 detected at {current}")
                    broken_links.append((current, current, resp.status_code))
                    if len(broken_links) >= ERROR_LIMIT:
                        print(f"[DEBUG] Error limit reached after processing {current}.")
                        return
                    continue
                soup = BeautifulSoup(resp.text, 'html.parser')
                for a in soup.find_all('a', href=True):
                    # エラー件数チェック
                    if len(broken_links) >= ERROR_LIMIT:
                        print(f"[DEBUG] Error limit reached during link extraction.")
                        return
                    link = urljoin(current, a['href'])
                    link = urlparse(link)._replace(fragment="").geturl()
                    print(f"[DEBUG] Found link: {link}")
                    # 外部リンクの場合、参照元を current としてチェック
                    if not is_internal_link(link):
                        check_status(link, current)
                        if len(broken_links) >= ERROR_LIMIT:
                            print(f"[DEBUG] Error limit reached during external link check.")
                            return
                    if link not in visited:
                        queue.append(link)
            except Exception as e:
                print(f"[DEBUG] Exception while processing {current}: {e}")
                broken_links.append((current, current, f"Error: {str(e)}"))
                if len(broken_links) >= ERROR_LIMIT:
                    print(f"[DEBUG] Error limit reached after exception in {current}.")
                    return
        else:
            check_status(current, None)
            if len(broken_links) >= ERROR_LIMIT:
                print(f"[DEBUG] Error limit reached after checking non-internal link.")
                return

def check_status(url, source):
    # エラー件数上限を確認
    if len(broken_links) >= ERROR_LIMIT:
        return
    try:
        r = requests.head(url, headers=HEADERS, timeout=5)
        print(f"[DEBUG] Checking external URL: {url} - Status: {r.status_code}")
        if r.status_code == 404:
            ref = source if source else url
            print(f"[DEBUG] 404 detected at external URL: {url} (ref: {ref})")
            broken_links.append((ref, url, r.status_code))
    except Exception as e:
        ref = source if source else url
        print(f"[DEBUG] Exception while checking {url}: {e}")
        broken_links.append((ref, url, f"Error: {str(e)}"))

def update_google_sheet(broken):
    """
    Google Sheets の A列に404（またはリンク切れ）URL、B列に検出元記事URLを追加する。
    """
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file("service_account.json", scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(GOOGLE_SHEET_ID).sheet1

    for source, url, status in broken:
        row = [url, source]
        print(f"[DEBUG] Appending row to sheet: {row}")
        sheet.append_row(row)

def send_slack_notification(broken):
    if not SLACK_WEBHOOK_URL:
        print("SLACK_WEBHOOK_URL is not set.")
        return

    count = len(broken)
    sheets_url = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/edit?gid=0"
    msg = f"【404チェック結果】\n404が {count} 件検出されました。\nこちらよりエラーURLを確認してください。\n({sheets_url})"

    try:
        r = requests.post(SLACK_WEBHOOK_URL, json={"text": msg}, headers=HEADERS, timeout=10)
        if r.status_code not in [200, 204]:
            print(f"[DEBUG] Slack notification failed with status {r.status_code}: {r.text}")
    except Exception as e:
        print(f"[DEBUG] Slack notification failed: {e}")

def main():
    print(f"Starting crawl from {START_URL}")
    crawl(START_URL)
    print("Crawl finished.")
    print(f"Detected {len(broken_links)} broken links.")
    update_google_sheet(broken_links)
    send_slack_notification(broken_links)

if __name__ == "__main__":
    main()

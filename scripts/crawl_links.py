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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

# Slack Webhook 用の設定
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
# Google Sheets 用の設定（シートIDのみを指定する）
GOOGLE_SHEET_ID = "1DrEs-tAk2zlqKXBzVIwl2cbo_m7x39ySCKUjg7y_o7I"  # 実際のシートIDに置き換える


def is_internal_link(url):
    """
    URL が内部リンク(good-apps.jp)かどうかを判定
    """
    parsed = urlparse(url)
    return (parsed.netloc == "" or parsed.netloc.endswith(BASE_DOMAIN))


def is_excluded_domain(url):
    """
    チェック対象から除外したいドメインを判定する関数。
    例：Google 系ドメインなど、404 チェック不要のものはここで弾く。
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    # 今回は「google 関連」全般を除外として例示。不要に応じて追加/変更可能。
    exclude_keywords = [
        "google.com",
        "google.co.jp",
        "gstatic.com",
        "g.co",
        "youtu.be",
        "youtube.com",
        # 他にも必要に応じて・・・
    ]
    return any(k in domain for k in exclude_keywords)


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

                    # 外部リンクの場合、Google 系ドメインなどは除外
                    if not is_internal_link(link):
                        if is_excluded_domain(link):
                            # 除外ドメインならステータスチェックせずスキップ
                            continue
                        # 除外対象外の外部リンクならステータスチェック
                        check_status(link, current)
                        if len(broken_links) >= ERROR_LIMIT:
                            print(f"[DEBUG] Error limit reached during external link check.")
                            return

                    # 内部リンクかつ未訪問であれば、キューに追加
                    if is_internal_link(link) and link not in visited:
                        queue.append(link)

            except Exception as e:
                print(f"[DEBUG] Exception while processing {current}: {e}")
                broken_links.append((current, current, f"Error: {str(e)}"))
                if len(broken_links) >= ERROR_LIMIT:
                    print(f"[DEBUG] Error limit reached after exception in {current}.")
                    return
        else:
            # 内部リンク以外だが、キューに入ってしまった場合の予備チェック
            # ただし、除外ドメインならスキップ
            if is_excluded_domain(current):
                continue
            check_status(current, None)
            if len(broken_links) >= ERROR_LIMIT:
                print(f"[DEBUG] Error limit reached after checking non-internal link.")
                return


def check_status(url, source):
    """
    指定URLのステータスを HEAD リクエストでチェックし、必要なら GET も行う。
    404 であれば broken_links に記録する。
    """
    try:
        r = requests.head(url, headers=HEADERS, timeout=5)
        if r.status_code == 404:
            broken_links.append((source or url, url, 404))
        elif r.status_code in (403, 405):
            # HEADが拒否された可能性があるため GET で再確認
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code == 404:
                broken_links.append((source or url, url, 404))
    except Exception as e:
        # ネットワークエラーなどの場合はここに来る
        # 404とは限らないので「broken_links」に入れるかは要検討
        print(f"[DEBUG] Exception in check_status for {url}: {e}")
        pass


def update_google_sheet(broken):
    """
    Google Sheets の A列に404（またはリンク切れ）URL、B列に検出元記事URL、
    C列以降にステータス等を追加するなど拡張可能。
    """
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
    print(f"Starting crawl from {START_URL}")
    crawl(START_URL)
    print("Crawl finished.")
    print(f"Detected {len(broken_links)} broken links.")
    update_google_sheet(broken_links)
    send_slack_notification(broken_links)


if __name__ == "__main__":
    main()

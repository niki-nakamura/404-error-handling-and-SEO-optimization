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


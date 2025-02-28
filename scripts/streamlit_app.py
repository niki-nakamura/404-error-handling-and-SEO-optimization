import streamlit as st
import pandas as pd
import json
import os
import subprocess
from datetime import datetime

CSV_FILE = "broken_links.csv"
JSON_FILE = "resolved_links.json"

# リポジトリ push 用の環境変数
# 例: secrets.GITHUB_TOKEN, or personal PAT
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO_URL = "https://github.com/USER/404-error-handling-and-SEO-optimization.git"  # あなたのリポジトリURLに置き換え
BRANCH_NAME = "main"

st.title("404リンク管理アプリ (CSV + JSON + Git履歴)")

# ▼ 1) broken_links.csv を読み込み
if not os.path.exists(CSV_FILE):
    st.warning("まだ404リンク情報がありません。クローラー未実行 or CI未完了かもしれません。")
    st.stop()

df_404 = pd.read_csv(CSV_FILE)

# ▼ 2) resolved_links.json を読み込み or 空生成
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    resolved_records = data.get("resolved", [])
else:
    resolved_records = []

df_resolved = pd.DataFrame(resolved_records)
for col in ["source", "url", "resolved", "resolved_date"]:
    if col not in df_resolved.columns:
        if col in ["source", "url", "resolved_date"]:
            df_resolved[col] = ""
        elif col == "resolved":
            df_resolved[col] = False

# ▼ 3) マージして表示用 DataFrame を用意
merged_df = pd.merge(
    df_404, df_resolved,
    on=["source", "url"],
    how="left"
)
merged_df["resolved"] = merged_df["resolved"].fillna(False)
merged_df["resolved_date"] = merged_df["resolved_date"].fillna("")

filter_option = st.radio(
    "表示フィルタ:",
    ("すべて", "未解決のみ", "解決済みのみ")
)
if filter_option == "未解決のみ":
    view_df = merged_df[merged_df["resolved"] == False]
elif filter_option == "解決済みのみ":
    view_df = merged_df[merged_df["resolved"] == True]
else:
    view_df = merged_df

st.write("▼ 以下のテーブルでチェックを編集すると、更新ボタン押下で JSON & Git に記録します。")

# (Streamlit 1.25+ の LinkColumn)
column_config = {
    "source": st.column_config.LinkColumn("Source"),
    "url": st.column_config.LinkColumn("URL"),
}

edited_df = st.data_editor(
    view_df,
    column_config=column_config,
    use_container_width=True
)

# ▼ 4) 「ステータス更新」ボタンを押すたびに JSON 更新 & コミットプッシュ
if st.button("ステータス更新"):
    updated_list = []
    for idx, row in edited_df.iterrows():
        updated_list.append({
            "source": row["source"],
            "url": row["url"],
            "resolved": bool(row["resolved"]),
            "resolved_date": row.get("resolved_date", "")
        })

    # resolved=True にしたら日付埋めるなどの運用
    for item in updated_list:
        if item["resolved"] and not item["resolved_date"]:
            item["resolved_date"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        elif not item["resolved"]:
            item["resolved_date"] = ""

    # merged_df 全体に反映する（フィルタで見えてない行も考慮したければ merge するなど）
    new_map = { (r["source"], r["url"]) : r for r in updated_list }

    final_rows = []
    for _, row in merged_df.iterrows():
        key = (row["source"], row["url"])
        if key in new_map:
            rec = new_map[key]
            final_rows.append({
                "source": row["source"],
                "url": row["url"],
                "resolved": rec["resolved"],
                "resolved_date": rec["resolved_date"]
            })
        else:
            final_rows.append({
                "source": row["source"],
                "url": row["url"],
                "resolved": row["resolved"],
                "resolved_date": row["resolved_date"]
            })

    out_data = {"resolved": final_rows}
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)

    st.success("JSONファイルを更新しました。Gitリポジトリへコミット＆プッシュを行います。")

    # ▼ 4-1) Git コマンドでコミット & プッシュ (要トークン設定)
    try:
        # もしクローン済みなら既に .git があり、ローカルにリポジトリ情報がある前提
        # GITHUB_TOKEN がある場合は、下記のようにリモートURLを書き換え
        if GITHUB_TOKEN:
            # 例: https://<token>@github.com/USER/REPO.git
            remote_url = REPO_URL.replace("https://", f"https://{GITHUB_TOKEN}@")
        else:
            # トークン未設定 → そのまま push (公開リポジトリならID/PW要求 or 失敗)
            remote_url = REPO_URL

        # git add
        subprocess.run(["git", "add", JSON_FILE], check=True)
        # git commit
        subprocess.run(["git", "commit", "-m", "Update resolved_links.json [skip ci]"], check=True)
        # git push
        subprocess.run(["git", "push", remote_url, f"HEAD:{BRANCH_NAME}"], check=True)

        st.info("コミット & プッシュが完了しました。リポジトリを確認してください。")

    except subprocess.CalledProcessError as e:
        st.error(f"Gitコマンドの実行に失敗: {e}")

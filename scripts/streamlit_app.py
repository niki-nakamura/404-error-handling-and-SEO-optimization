import streamlit as st
import pandas as pd
import json
import os
import subprocess
from datetime import datetime

CSV_FILE = "broken_links.csv"
JSON_FILE = "resolved_links.json"

st.title("404リンク管理アプリ (JSONログ + Gitコミット版) - リアルタイム更新")

# 1) CSVを読み込み
if not os.path.exists(CSV_FILE):
    st.warning("まだ404リンク情報がありません。")
    st.stop()
df_404 = pd.read_csv(CSV_FILE)

# 2) JSONを読み込み / 空
resolved_records = []
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        resolved_records = data.get("resolved", [])
df_resolved = pd.DataFrame(resolved_records, columns=["source","url","resolved","resolved_date"])

# 必要列がなければ補完
for col in ["source","url","resolved","resolved_date"]:
    if col not in df_resolved.columns:
        if col in ["source","url","resolved_date"]:
            df_resolved[col] = ""
        elif col == "resolved":
            df_resolved[col] = False

# 3) merged_df 作成
merged_df = pd.merge(df_404, df_resolved, on=["source","url"], how="left")
merged_df["resolved"] = merged_df["resolved"].fillna(False)
merged_df["resolved_date"] = merged_df["resolved_date"].fillna("")

# 3.5) source == url は自動で resolved=True とする
auto_resolve_mask = merged_df["source"] == merged_df["url"]
merged_df.loc[auto_resolve_mask, "resolved"] = True

# resolved_date が未設定なら現在日時を入れる
date_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
merged_df.loc[auto_resolve_mask & (merged_df["resolved_date"] == ""), "resolved_date"] = date_now

# 4) フィルタ
filter_option = st.radio("表示フィルタ:", ["すべて","未解決のみ","解決済みのみ"])
if filter_option == "未解決のみ":
    show_df = merged_df[merged_df["resolved"] == False]
elif filter_option == "解決済みのみ":
    show_df = merged_df[merged_df["resolved"] == True]
else:
    show_df = merged_df

st.write("▼ チェックボックスを変更すると自動で JSON 更新と Git push が行われます。")

# 5) data_editor で表示
edited_df = st.data_editor(show_df, use_container_width=True, key="editor")

# 6) 変更を検知し、自動で JSON & Git に反映
def save_and_push_changes(updated: pd.DataFrame):
    """
    1. フィルタされている行 only → merged_df に戻して全行まとめる
    2. JSON 書き込み
    3. git commit & push（差分があるときだけ）
    """
    # a) updated の (source, url) を dict 化
    new_map = {}
    for _, row in updated.iterrows():
        # resolved_date の補完
        if row["resolved"] and not row["resolved_date"]:
            row["resolved_date"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        elif not row["resolved"]:
            row["resolved_date"] = ""
        new_map[(row["source"], row["url"])] = dict(row)

    # b) merged_df に再適用
    final_rows = []
    for _, row in merged_df.iterrows():
        key = (row["source"], row["url"])
        if key in new_map:
            final_rows.append({
                "source": row["source"],
                "url": row["url"],
                "resolved": new_map[key]["resolved"],
                "resolved_date": new_map[key]["resolved_date"]
            })
        else:
            final_rows.append({
                "source": row["source"],
                "url": row["url"],
                "resolved": row["resolved"],
                "resolved_date": row["resolved_date"]
            })

    # c) JSON書き込み
    out_data = {"resolved": final_rows}
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)
    st.info("resolved_links.json に自動保存しました。Gitにプッシュを行います...")

    # d) git commit & push
    subprocess.run(["git", "config", "user.name", "github-actions"], check=True)
    subprocess.run(["git", "config", "user.email", "github-actions@github.com"], check=True)

    # 変更があるかを確認する（diffがあれば returncode != 0）
    diff_result = subprocess.run(["git", "diff", "--exit-code", JSON_FILE])
    if diff_result.returncode != 0:
        # 変更あり → commit & push
        subprocess.run(["git", "add", JSON_FILE], check=True)
        subprocess.run(["git", "commit", "-m", "Auto update resolved_links.json [skip ci]"], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        st.success("Gitコミット＆プッシュが完了しました。リポジトリを確認してください。")
    else:
        # 変更が無い場合はcommitしない
        st.info("変更が無いためコミットをスキップしました。")

# 7) セッション状態に前回の DataFrame を保持し、差分があれば保存・プッシュ
if "last_edited_df" not in st.session_state:
    st.session_state["last_edited_df"] = edited_df.copy()
else:
    # data_editor はユーザー操作のたび再実行 → 変更を検知
    if not edited_df.equals(st.session_state["last_edited_df"]):
        # 変更があったため、自動保存とpush
        save_and_push_changes(edited_df)
        # 新しい状態をセッションに保存
        st.session_state["last_edited_df"] = edited_df.copy()

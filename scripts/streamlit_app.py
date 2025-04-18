import streamlit as st
import pandas as pd
import json
import os
import subprocess
from datetime import datetime

CSV_FILE = "broken_links.csv"
JSON_FILE = "resolved_links.json"

st.title("404リンク管理アプリ")

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

for col in ["source","url","resolved","resolved_date"]:
    if col not in df_resolved.columns:
        if col in ["source","url","resolved_date"]:
            df_resolved[col] = ""
        elif col == "resolved":
            df_resolved[col] = False

merged_df = pd.merge(df_404, df_resolved, on=["source","url"], how="left")
merged_df["resolved"] = merged_df["resolved"].fillna(False)
merged_df["resolved_date"] = merged_df["resolved_date"].fillna("")

auto_resolve_mask = merged_df["source"] == merged_df["url"]
merged_df.loc[auto_resolve_mask, "resolved"] = True
date_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
merged_df.loc[auto_resolve_mask & (merged_df["resolved_date"] == ""), "resolved_date"] = date_now

filter_option = st.radio("表示フィルタ:", ["すべて","未解決のみ","解決済みのみ"])
if filter_option == "未解決のみ":
    show_df = merged_df[merged_df["resolved"] == False]
elif filter_option == "解決済みのみ":
    show_df = merged_df[merged_df["resolved"] == True]
else:
    show_df = merged_df

st.write("▼ チェックボックスを変更すると自動で JSON 更新と Git push が行われます。")

# ★ここ：CSS を埋め込み
st.markdown(
    """
    <style>
    /* 
       data_editor 内部に "StyledDataEditor" や "stDataEditorContainer" 
       などのクラスがあるかをブラウザの開発ツールで確認し、合わせる 
    */
    [class*="StyledDataEditor"] table {
        border: none !important;
        border-collapse: collapse;
    }

    /* ヘッダ部分を薄い線に変更・背景色をつける */
    [class*="StyledDataEditor"] thead th {
        background-color: #f9f9f9 !important;
        border-bottom: 1px solid #ccc !important;
        font-weight: bold !important;
    }

    /* ボディ部分のセルの線を消す or 薄くする */
    [class*="StyledDataEditor"] tbody td {
        border: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

edited_df = st.data_editor(show_df, use_container_width=True, key="editor")

def save_and_push_changes(updated: pd.DataFrame):
    ...
    # (既存の処理はそのまま)

if "last_edited_df" not in st.session_state:
    st.session_state["last_edited_df"] = edited_df.copy()
else:
    if not edited_df.equals(st.session_state["last_edited_df"]):
        save_and_push_changes(edited_df)
        st.session_state["last_edited_df"] = edited_df.copy()

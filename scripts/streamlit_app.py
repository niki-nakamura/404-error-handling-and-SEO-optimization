import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime

CSV_FILE = "broken_links.csv"
JSON_FILE = "resolved_links.json"

st.title("404リンク管理アプリ (JSON ログ分離)")

# CSV が無ければ停止
if not os.path.exists(CSV_FILE):
    st.warning("まだ404リンク情報がありません。")
    st.stop()

df_404 = pd.read_csv(CSV_FILE)

# JSON を読み込み or 空
resolved_records = []
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        resolved_records = data.get("resolved", [])
df_resolved = pd.DataFrame(resolved_records, columns=["source","url","resolved","resolved_date"])

# 欠けてる列を作る
for col in ["source", "url", "resolved", "resolved_date"]:
    if col not in df_resolved.columns:
        if col in ["source","url","resolved_date"]:
            df_resolved[col] = ""
        else:
            df_resolved[col] = False

# merge
merged_df = pd.merge(df_404, df_resolved, on=["source","url"], how="left")
merged_df["resolved"] = merged_df["resolved"].fillna(False)
merged_df["resolved_date"] = merged_df["resolved_date"].fillna("")

# UI
filter_option = st.radio("表示フィルタ:", ("すべて","未解決のみ","解決済みのみ"))
if filter_option == "未解決のみ":
    view_df = merged_df[merged_df["resolved"] == False]
elif filter_option == "解決済みのみ":
    view_df = merged_df[merged_df["resolved"] == True]
else:
    view_df = merged_df

edited_df = st.data_editor(view_df, use_container_width=True)

if st.button("ステータス更新"):
    # edited_df の情報を new_map にまとめる
    new_map = {}
    for idx, row in edited_df.iterrows():
        r = dict(row)
        if r["resolved"] and not r["resolved_date"]:
            r["resolved_date"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        elif not r["resolved"]:
            r["resolved_date"] = ""
        new_map[(r["source"],r["url"])] = r

    final_rows = []
    for _, row in merged_df.iterrows():
        key = (row["source"],row["url"])
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

    out_data = {"resolved": final_rows}
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)

    st.success("resolved_links.json に書き込み完了 (まだ git push はしない)")

import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime

CSV_FILE = "broken_links.csv"
JSON_FILE = "resolved_links.json"

st.title("404リンク管理アプリ (CSV + JSON 分離版)")
st.write("CSV には最新の404リンク一覧を自動生成し、チェック状態は JSON に記録して保持")

# 1. broken_links.csv を読み込み (存在しない場合は警告)
if not os.path.exists(CSV_FILE):
    st.warning("まだ404リンク情報がありません。クローラー未実行、またはCIが未完了です。")
    st.stop()

df_404 = pd.read_csv(CSV_FILE)

# 2. resolved_links.json を読み込み (無ければ空リスト)
resolved_records = []
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        resolved_records = data.get("resolved", [])
else:
    resolved_records = []

df_resolved = pd.DataFrame(resolved_records)

# 必要な列が無ければ補完 (source/url/resolved/resolved_date)
if "source" not in df_resolved.columns:
    df_resolved["source"] = ""
if "url" not in df_resolved.columns:
    df_resolved["url"] = ""
if "resolved" not in df_resolved.columns:
    df_resolved["resolved"] = False
if "resolved_date" not in df_resolved.columns:
    df_resolved["resolved_date"] = ""

# 3. df_404 と df_resolved をキー (source, url) でマージ
merged_df = pd.merge(
    df_404, df_resolved,
    on=["source", "url"],
    how="left"
)

# merged_df["resolved"], merged_df["resolved_date"] が NaN の場合を初期化
merged_df["resolved"] = merged_df["resolved"].fillna(False)
merged_df["resolved_date"] = merged_df["resolved_date"].fillna("")

# 4. フィルタUI
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

st.write("▼ 以下のテーブルでリンクの解決状況を管理できます。")

# (Streamlit 1.25+ のLinkColumnを使う例。うまく動かない場合は単純に列表示)
column_config = {
    "source": st.column_config.LinkColumn("Source"),
    "url": st.column_config.LinkColumn("URL"),
}

edited_df = st.data_editor(
    view_df,
    column_config=column_config,
    use_container_width=True
)

# 5. 「ステータス更新」ボタン → JSON更新
if st.button("ステータス更新"):
    # edited_df は現在のフィルタ後のみ。全レコードを更新するためには merged_df の状態も考慮
    # 簡易方法: フィルタ中のデータのみ更新
    updated_list = []
    for idx, row in edited_df.iterrows():
        updated_list.append({
            "source": row["source"],
            "url": row["url"],
            "resolved": bool(row["resolved"]),
            "resolved_date": row.get("resolved_date", "")
        })

    # resolved を True にした時点で日付が無ければ現在時刻を入れる例
    for item in updated_list:
        if item["resolved"] and not item["resolved_date"]:
            item["resolved_date"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        elif not item["resolved"]:
            # resolved=False に戻したら日付を消すなどの運用も可能
            item["resolved_date"] = ""

    # updated_list を df にし、元 merged_df と付き合わせて最終反映
    update_df = pd.DataFrame(updated_list)

    # すべての merged_df 行に対して update_df の値をマージ
    new_map = {
        (r["source"], r["url"]): {
            "resolved": r["resolved"],
            "resolved_date": r["resolved_date"]
        }
        for _, r in update_df.iterrows()
    }

    final_rows = []
    for _, row in merged_df.iterrows():
        key = (row["source"], row["url"])
        if key in new_map:
            # 更新された
            final_rows.append({
                "source": row["source"],
                "url": row["url"],
                "resolved": new_map[key]["resolved"],
                "resolved_date": new_map[key]["resolved_date"],
            })
        else:
            # 編集されていない → そのまま
            final_rows.append({
                "source": row["source"],
                "url": row["url"],
                "resolved": row["resolved"],
                "resolved_date": row["resolved_date"],
            })

    # JSONへの書き込み
    out_data = {"resolved": final_rows}
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)

    st.success("チェック状態を JSON に保存しました。")
    st.experimental_rerun()

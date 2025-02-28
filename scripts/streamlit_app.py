import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime

CSV_FILE = "broken_links.csv"
JSON_FILE = "resolved_links.json"

st.title("404リンク管理アプリ (自動保存版)")
st.write("""
CSV には最新の404リンク一覧を自動生成し、チェック状態は JSON に記録して保持します。
チェックボックスを変更するたびに JSON が自動更新されます。
""")

# ▼ 1) CSVを読み込み （無ければ停止）
if not os.path.exists(CSV_FILE):
    st.warning("まだ404リンク情報がありません。クローラー未実行 or CI未完了の可能性。")
    st.stop()

df_404 = pd.read_csv(CSV_FILE)

# ▼ 2) JSONを読み込み。無ければ空リスト。
resolved_records = []
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        resolved_records = data.get("resolved", [])
else:
    resolved_records = []

df_resolved = pd.DataFrame(resolved_records)

# ▼ 必要な列を作る（空の状態に備える）
for col in ["source", "url", "resolved", "resolved_date"]:
    if col not in df_resolved.columns:
        # 型に合わせて初期化
        if col in ["source", "url", "resolved_date"]:
            df_resolved[col] = ""
        elif col == "resolved":
            df_resolved[col] = False

# ▼ 3) df_404 と df_resolved を (source, url) でマージ
merged_df = pd.merge(
    df_404, df_resolved,
    on=["source", "url"],
    how="left"
)

# もし merged_df["resolved"] が NaN の場合、Falseに
merged_df["resolved"] = merged_df["resolved"].fillna(False)
# もし merged_df["resolved_date"] が NaN の場合、空文字に
merged_df["resolved_date"] = merged_df["resolved_date"].fillna("")

# ▼ 4) フィルタ
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

st.write("▼ 以下のテーブルでリンク状態を編集すると、自動で保存されます。")

# LinkColumn が使える場合の設定 (Streamlit 1.25+)
column_config = {
    "source": st.column_config.LinkColumn("Source"),
    "url": st.column_config.LinkColumn("URL"),
}

# ▼ 5) data_editor（ボタン無し）
edited_df = st.data_editor(
    view_df,
    column_config=column_config,
    use_container_width=True,
    key="editor"  # セッション管理用キーを付けておくと良い
)

# ここがポイント:
# 「ユーザーがチェックを変える」→ Streamlit が再実行 → 下記コードが走る → JSONを更新
def update_json_from_edited(edited):
    # st.data_editor で返された DataFrame(edited) に含まれる行だけ更新する
    updated_list = []
    for idx, row in edited.iterrows():
        updated_list.append({
            "source": row["source"],
            "url": row["url"],
            "resolved": bool(row["resolved"]),
            "resolved_date": row.get("resolved_date", "")
        })

    # resolved=True にしたら日付をセット、False なら空にする等の運用
    for item in updated_list:
        if item["resolved"] and not item["resolved_date"]:
            item["resolved_date"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        elif not item["resolved"]:
            item["resolved_date"] = ""

    # ▲ フィルタにより一部のみ行が来ているので、merged_df 全体に反映する
    # あるいは簡略化として「今表示中の行のみ保存する」という運用でもOK
    new_map = {
        (r["source"], r["url"]): {
            "resolved": r["resolved"],
            "resolved_date": r["resolved_date"]
        }
        for r in updated_list
    }

    # merged_df に戻し→ JSON 全体を再生成
    final_rows = []
    for _, row in merged_df.iterrows():
        key = (row["source"], row["url"])
        if key in new_map:
            final_rows.append({
                "source": row["source"],
                "url": row["url"],
                "resolved": new_map[key]["resolved"],
                "resolved_date": new_map[key]["resolved_date"],
            })
        else:
            final_rows.append({
                "source": row["source"],
                "url": row["url"],
                "resolved": row["resolved"],
                "resolved_date": row["resolved_date"],
            })

    out_data = {"resolved": final_rows}
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)

    st.info("変更内容を自動保存しました。")

# ▼ 6) セッション状態を使い「前回の DataFrame」と比較し、差分があれば JSONを更新
if "last_df" not in st.session_state:
    # 初回読み込み時はとりあえず記憶しておく
    st.session_state["last_df"] = edited_df.copy()
else:
    # もし edited_df が前回と違えば更新
    if not edited_df.equals(st.session_state["last_df"]):
        update_json_from_edited(edited_df)
        st.session_state["last_df"] = edited_df.copy()

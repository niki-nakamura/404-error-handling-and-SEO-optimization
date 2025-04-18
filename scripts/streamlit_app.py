import streamlit as st
import pandas as pd
import json
import os
import subprocess
from datetime import datetime

CSV_FILE = "broken_links.csv"
JSON_FILE = "resolved_links.json"

st.title("404リンク管理アプリ")

# ========== 1) CSVファイル読み込み ==========
if not os.path.exists(CSV_FILE):
    st.warning("まだ404リンク情報がありません。")
    st.stop()

df_404 = pd.read_csv(CSV_FILE)

# ========== 2) 解決状況を記録する JSON を読み込み ==========
resolved_records = []
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        resolved_records = data.get("resolved", [])

df_resolved = pd.DataFrame(resolved_records, columns=["source","url","resolved","resolved_date"])

# 必要な列が無ければ補完
for col in ["source","url","resolved","resolved_date"]:
    if col not in df_resolved.columns:
        # 日付列やURL列は空文字, bool列は False で初期化
        if col in ["source","url","resolved_date"]:
            df_resolved[col] = ""
        elif col == "resolved":
            df_resolved[col] = False

# ========== 3) merged_df (404リスト + 解決情報) を作成 ==========
merged_df = pd.merge(df_404, df_resolved, on=["source","url"], how="left")
merged_df["resolved"] = merged_df["resolved"].fillna(False)
merged_df["resolved_date"] = merged_df["resolved_date"].fillna("")

# (オプション) source と url が同じ場合は自動で resolved=True にする
auto_resolve_mask = merged_df["source"] == merged_df["url"]
merged_df.loc[auto_resolve_mask, "resolved"] = True

date_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
merged_df.loc[auto_resolve_mask & (merged_df["resolved_date"] == ""), "resolved_date"] = date_now

# ========== 4) 表示フィルタ (ラジオボタン) ==========
filter_option = st.radio("表示フィルタ:", ["すべて", "未解決のみ", "解決済みのみ"])
if filter_option == "未解決のみ":
    show_df = merged_df[merged_df["resolved"] == False].copy()
elif filter_option == "解決済みのみ":
    show_df = merged_df[merged_df["resolved"] == True].copy()
else:
    show_df = merged_df.copy()

st.write("▼ チェックボックスを変更すると自動で JSON 更新と Git push が行われます。")

# ========== 5) HTML 表示用にテーブルを生成 & 行ごとのチェックボックスを配置 ==========
# ここでは、行のチェックボックスを並べて「resolved」の真偽を切り替えます。
# 表示をカスタマイズしたい場合、CSS 等を組み合わせたよりリッチなテーブル表示にもできます。

# セッションに保存しておく
if "cache_show_df" not in st.session_state:
    st.session_state["cache_show_df"] = show_df.copy()

st.markdown("""
<style>
table {
    width: 100%;
    border-collapse: collapse;
}
th, td {
    text-align: left;
    padding: 6px;
    border: 1px solid #ccc;
}
</style>
""", unsafe_allow_html=True)

# HTMLテーブルのヘッダ部分
table_html = """
<table>
    <thead>
      <tr>
        <th style="width:5%">No.</th>
        <th style="width:40%">Source</th>
        <th style="width:40%">URL</th>
        <th style="width:10%">Resolved?</th>
      </tr>
    </thead>
    <tbody>
"""

# Streamlit のチェックボックスとHTMLテーブルを組み合わせるには、
# 1行ごとに st.checkbox を呼び出し、HTMLは文字列結合する形で進めます。
updated_data = []
changed = False

for i, row in show_df.reset_index(drop=True).iterrows():
    # rowごとにチェックボックスを配置
    checkbox_key = f"row_{i}"  # ユニークキー
    current_resolved_value = row["resolved"]
    new_state = st.checkbox(" ", value=current_resolved_value, key=checkbox_key)

    # 状態が変わったか確認
    if new_state != current_resolved_value:
        changed = True
    
    # 表示用にHTMLテーブルの行を追加 (チェックボックスは Streamlit 側に表示)
    table_html += f"""
      <tr>
        <td>{i+1}</td>
        <td>{row["source"]}</td>
        <td>{row["url"]}</td>
        <td>{'✔' if new_state else '✕'}</td>
      </tr>
    """

    # 行の情報を更新用リストに保存
    # resolved_date の補完もここで行う
    row_dict = row.to_dict()
    row_dict["resolved"] = new_state
    if new_state and not row_dict["resolved_date"]:
        row_dict["resolved_date"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    elif not new_state:
        row_dict["resolved_date"] = ""
    updated_data.append(row_dict)

table_html += "</tbody></table>"
st.markdown(table_html, unsafe_allow_html=True)

# ========== 6) 変更があれば JSON & Git に反映 ==========
# 全行をマージして resolved_links.json を再生成する

def save_and_push_changes(updated_rows):
    # a) show_df でフィルタされた行の更新情報を merged_df に反映
    #    → すべての行をまとめて JSON へ書き出すため
    # キー( source, url )で merged_df をアップデートしていく
    merged_final = merged_df.copy()
    updated_map = {(r["source"], r["url"]): r for r in updated_rows}

    final_rows = []
    for idx, mrow in merged_final.iterrows():
        key = (mrow["source"], mrow["url"])
        if key in updated_map:
            final_rows.append({
                "source": mrow["source"],
                "url": mrow["url"],
                "resolved": updated_map[key]["resolved"],
                "resolved_date": updated_map[key]["resolved_date"]
            })
        else:
            # フィルタ外の行はそのまま
            final_rows.append({
                "source": mrow["source"],
                "url": mrow["url"],
                "resolved": mrow["resolved"],
                "resolved_date": mrow["resolved_date"]
            })

    # b) JSON書き込み
    out_data = {"resolved": final_rows}
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)
    st.info("resolved_links.json に自動保存しました。Gitにプッシュを行います...")

    # c) Git コミット & プッシュ
    subprocess.run(["git", "config", "user.name", "github-actions"], check=True)
    subprocess.run(["git", "config", "user.email", "github-actions@github.com"], check=True)

    diff_result = subprocess.run(["git", "diff", "--exit-code", JSON_FILE])
    if diff_result.returncode != 0:
        # 変更あり → commit & push
        subprocess.run(["git", "add", JSON_FILE], check=True)
        subprocess.run(["git", "commit", "-m", "Auto update resolved_links.json [skip ci]"], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        st.success("Gitコミット＆プッシュが完了しました。リポジトリを確認してください。")
    else:
        st.info("変更が無いためコミットをスキップしました。")

# 変更があれば保存を実行
if changed:
    save_and_push_changes(updated_data)
    st.session_state["cache_show_df"] = show_df.copy()

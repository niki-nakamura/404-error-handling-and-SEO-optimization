import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime

CSV_FILE = "broken_links.csv"
JSON_FILE = "resolved_links.json"

st.title("404リンク管理アプリ (CSV + JSON 分離版)")
st.write("CSV: 最新の 404 リンクのみ、JSON: 解決状況のログを保持")

# 1. 最新の404情報をCSVから読み込む
if not os.path.exists(CSV_FILE):
    st.warning("まだ404リンク情報がありません。クローラー未実行またはCI未完了の可能性。")
    st.stop()

df_404 = pd.read_csv(CSV_FILE)

# 2. JSONファイル (resolved_links.json) を読み込み・DataFrame化
resolved_records = []
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        # data の構造が {"resolved": [ {source, url, resolved, resolved_date}, ... ]} である想定
        resolved_records = data.get("resolved", [])

df_resolved = pd.DataFrame(resolved_records)

# 3. マージ
#    df_404: [source, url, status, detected_date]
#    df_resolved: [source, url, resolved, resolved_date]  (任意で追加情報OK)
#    キー: (source, url)
#    how="left" で 404 の一覧に対して resolved 状況を左結合
if "resolved" not in df_resolved.columns:
    df_resolved["resolved"] = False
if "resolved_date" not in df_resolved.columns:
    df_resolved["resolved_date"] = ""

merged_df = pd.merge(
    df_404, df_resolved,
    on=["source", "url"],
    how="left"
)

# マージの結果、resolved が NaN のものは False に初期化
merged_df["resolved"] = merged_df["resolved"].fillna(False)
merged_df["resolved_date"] = merged_df["resolved_date"].fillna("")

# フィルターUI
filter_option = st.radio("表示フィルター", ("すべて", "未解決のみ", "解決済みのみ"))
if filter_option == "未解決のみ":
    view_df = merged_df[merged_df["resolved"] == False]
elif filter_option == "解決済みのみ":
    view_df = merged_df[merged_df["resolved"] == True]
else:
    view_df = merged_df

st.write("▼ 以下のテーブルで、リンクの解決状況を編集できます。")

# 表示用カラム設定 (Streamlit 1.25 で LinkColumn が使える場合)
column_config = {
    "source": st.column_config.LinkColumn("Source"),
    "url": st.column_config.LinkColumn("URL"),
}

edited_df = st.data_editor(
    view_df,
    column_config=column_config,
    use_container_width=True
)

# 更新ボタン押下時、 resolved_links.json を書き換え
if st.button("ステータス更新"):
    # いったん edited_df と df_404 の (source, url) を突き合わせて
    # resolved, resolved_date を resolved_links.json へ保存する

    updated_list = []
    for idx, row in edited_df.iterrows():
        updated_list.append({
            "source": row["source"],
            "url": row["url"],
            "resolved": bool(row["resolved"]),
            "resolved_date": row.get("resolved_date", "")
        })

    # しかし edited_df は フィルタ状態のものだけなので、表示されていない行も含め全行を更新したい場合には
    # フィルタ前の merged_df を用いる or `view_df` ではなく `merged_df` を data_editor に渡す
    # (ここでは簡易対応。必要に応じて全行を再度 df_404 + df_resolved で再走査してもOK)

    # resolved が True に変更されたタイミングで resolved_date をセット(任意)
    for record in updated_list:
        if record["resolved"] and record["resolved_date"] == "":
            record["resolved_date"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        elif not record["resolved"]:
            record["resolved_date"] = ""

    # JSON 用にデータ整形
    # 注意：一度 resolved=False に戻した時に resolved_date を消すなど、好みに応じて運用
    new_resolved_df = pd.DataFrame(updated_list)

    # まだ表示されていない(フィルタではじかれた)行も含めて全行が反映されるように
    # merged_df と突き合わせて union する例
    # -----------------------------
    # Convert new_resolved_df to dict for easy lookup
    new_map = {
        (r["source"], r["url"]): {
            "resolved": r["resolved"],
            "resolved_date": r["resolved_date"],
        }
        for _, r in new_resolved_df.iterrows()
    }

    final_rows = []
    # すべての merged_df の行をループし、updated_list に含まれない場合はそのまま
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
            # 既存のものをそのまま
            final_rows.append({
                "source": row["source"],
                "url": row["url"],
                "resolved": row["resolved"],
                "resolved_date": row["resolved_date"],
            })

    # JSONに書き込み
    out_data = {"resolved": final_rows}
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)

    st.success("チェック状態を JSON に保存しました。 (resolved_links.json)")

    # ページリロードして反映したい場合:
    st.experimental_rerun()

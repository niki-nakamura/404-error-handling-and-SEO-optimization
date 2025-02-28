import streamlit as st
import pandas as pd
import os

st.title("404リンク管理アプリ")
st.write("定期実行された 404 検知結果を可視化し、管理するツールです。")

csv_file = "broken_links.csv"

# CSVファイルが無ければ終了
if not os.path.exists(csv_file):
    st.warning("現在、404リンク情報はありません。")
    st.stop()

df = pd.read_csv(csv_file)

# カラムが足りない場合は補完
if "resolved" not in df.columns:
    df["resolved"] = False
if "detected_date" not in df.columns:
    df["detected_date"] = ""

# 表示フィルタ
filter_option = st.radio(
    "表示するデータのフィルタ:",
    ("すべて", "未解決のみ", "解決済みのみ")
)

if filter_option == "未解決のみ":
    show_df = df[df["resolved"] == False]
elif filter_option == "解決済みのみ":
    show_df = df[df["resolved"] == True]
else:
    show_df = df

st.write("▼ 以下のテーブルで、リンク状態を編集できます。")

# LinkColumn が未対応な場合は下記2行を外すか、単純な列表示にしてください
column_config = {
    "source": st.column_config.LinkColumn("Source"),
    "url": st.column_config.LinkColumn("URL"),
}

edited_df = st.data_editor(
    show_df,
    column_config=column_config,
    use_container_width=True
)

if st.button("ステータス更新"):
    # edited_df の状態を元 df に反映
    for idx, row in edited_df.iterrows():
        mask = (
            (df["source"] == row["source"]) &
            (df["url"] == row["url"])
        )
        df.loc[mask, "resolved"] = row["resolved"]

    # CSV上書き保存
    df.to_csv(csv_file, index=False)
    st.success("ステータスを更新しました。")

    # すぐ反映したい場合はセッションをリロード
    # st.experimental_rerun()

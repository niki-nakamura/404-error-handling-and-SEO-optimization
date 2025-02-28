import streamlit as st
import pandas as pd
import os

st.title("404リンク管理アプリ")
st.write("定期実行された 404 検知結果を可視化し、管理するツールです。")

csv_file = "broken_links.csv"

# CSVファイルがなければ終了
if not os.path.exists(csv_file):
    st.warning("現在、404リンク情報はありません。")
    st.stop()

# CSV読み込み
df = pd.read_csv(csv_file)

# 必要なカラムがなければ補完
if 'resolved' not in df.columns:
    df['resolved'] = False

if 'detected_date' not in df.columns:
    df['detected_date'] = ""

# フィルター切り替え
filter_option = st.radio(
    "表示するデータのフィルタ:",
    ("すべて", "未解決のみ", "解決済みのみ")
)

if filter_option == "未解決のみ":
    show_df = df[df['resolved'] == False]
elif filter_option == "解決済みのみ":
    show_df = df[df['resolved'] == True]
else:
    show_df = df

st.write("▼ 以下のテーブルで、リンク状態を編集できます。")

# 「source」「url」をクリック可能なリンクとして表示するための設定
# Streamlit 1.25+ の st.data_editor で有効
column_config = {
    "source": st.column_config.LinkColumn(
        "Source",
        url_expression="source",     # データフレーム上のカラム名を指定
        help="クリックでリンク先を開きます"
    ),
    "url": st.column_config.LinkColumn(
        "URL",
        url_expression="url",
        help="クリックでリンク先を開きます"
    )
}

edited_df = st.data_editor(
    show_df,
    column_config=column_config,
    use_container_width=True
)

# 更新ボタン押下時に 'resolved' の状態を更新
if st.button("ステータス更新"):
    for idx, row in edited_df.iterrows():
        mask = (df['url'] == row['url']) & (df['source'] == row['source'])
        df.loc[mask, 'resolved'] = row['resolved']

    df.to_csv(csv_file, index=False)
    st.success("ステータスを更新しました。")

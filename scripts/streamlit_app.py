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

# CSVを読み込み
df = pd.read_csv(csv_file)

# 'resolved' カラムが未作成なら初期Falseで作成
if 'resolved' not in df.columns:
    df['resolved'] = False

# 検出日カラムが存在しなければ追加
if 'detected_date' not in df.columns:
    df['detected_date'] = ""

# フィルタラジオボタン
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

# st.data_editor は Streamlit 1.22+ で利用可能
edited_df = st.data_editor(show_df, use_container_width=True)

# 更新ボタン押下時
if st.button("ステータス更新"):
    for idx, row in edited_df.iterrows():
        # 同じ source, url を持つ行を df から抽出して 'resolved' を更新
        mask = (df['url'] == row['url']) & (df['source'] == row['source'])
        df.loc[mask, 'resolved'] = row['resolved']

    df.to_csv(csv_file, index=False)
    st.success("ステータスを更新しました。")

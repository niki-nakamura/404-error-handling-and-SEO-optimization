import streamlit as st
import pandas as pd
import os

st.title("404リンク管理アプリ")
st.write("定期実行された 404 検知結果を可視化し、管理するツールです。")

csv_file = "broken_links.csv"
if not os.path.exists(csv_file):
    st.warning("現在、404リンク情報はありません。")
    st.stop()

df = pd.read_csv(csv_file)

# 必要カラムがなければ補完
if 'resolved' not in df.columns:
    df['resolved'] = False
if 'detected_date' not in df.columns:
    df['detected_date'] = ""

# フィルタ
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

# クリック可能リンクとして表示したい列を LinkColumn に指定
column_config = {
    "source": st.column_config.LinkColumn(
        label="Source",
        help="クリックでソース記事へ移動"
    ),
    "url": st.column_config.LinkColumn(
        label="URL",
        help="クリックでリンク先へ移動"
    ),
    # その他の列は自動設定 or 必要に応じて設定
}

edited_df = st.data_editor(
    show_df,
    column_config=column_config,
    use_container_width=True
)

# 解決状況の更新
if st.button("ステータス更新"):
    for idx, row in edited_df.iterrows():
        mask = (df['url'] == row['url']) & (df['source'] == row['source'])
        df.loc[mask, 'resolved'] = row['resolved']

    df.to_csv(csv_file, index=False)
    st.success("ステータスを更新しました。")

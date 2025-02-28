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

# Streamlit 1.25+ で有効になる LinkColumn 設定
# 'source' や 'url' の値をクリック可能なリンクにする
column_config = {
    "source": st.column_config.LinkColumn(
        label="Source",
        help="クリックでリンク先を開きます",
        href_pattern="{source}"  # カラム 'source' の値をリンクに利用
    ),
    "url": st.column_config.LinkColumn(
        label="URL",
        help="クリックでリンク先を開きます",
        href_pattern="{url}"     # カラム 'url' の値をリンクに利用
    ),
}

edited_df = st.data_editor(
    show_df,
    column_config=column_config,
    use_container_width=True
)

# 更新ボタン押下で resolved カラムを更新
if st.button("ステータス更新"):
    for idx, row in edited_df.iterrows():
        mask = (df["url"] == row["url"]) & (df["source"] == row["source"])
        df.loc[mask, "resolved"] = row["resolved"]

    df.to_csv(csv_file, index=False)
    st.success("ステータスを更新しました。")

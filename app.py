import streamlit as st
import pandas as pd
import plotly.express as px
from streamlit_gsheets import GSheetsConnection

# 設定頁面為寬版模式，適合嵌入 iframe
st.set_page_config(page_title="財經小聚儀表板", layout="wide", initial_sidebar_state="collapsed")

# 隱藏 Streamlit 預設的多餘邊距與選單，讓嵌入 Google Sites 更乾淨
hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .block-container {padding-top: 1rem; padding-bottom: 1rem; padding-left: 1rem; padding-right: 1rem;}
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

st.title("📈 財經小聚市場動態儀表板")

# 建立與 Google Sheets 的連線
# 備註：您的試算表共用權限需設為「知道連結的人均可檢視」
SHEET_URL = "https://docs.google.com/spreadsheets/d/1yyh4nLraAxyeKEbvwJPQsdcb0YrTJ5b1LfIsUXD4n94/edit#gid=0"

conn = st.connection("gsheets", type=GSheetsConnection)

try:
    # 讀取 Dashboard 頁籤（跳過前兩行標題資訊）
    df = conn.read(spreadsheet=SHEET_URL, worksheet="Dashboard", skiprows=2, ttl="10m")
    
    # 週期篩選控制項
    periods = {
        "14天": "14天漲跌幅",
        "30天": "30天漲跌幅",
        "90天": "90天漲跌幅",
        "1年 (365天)": "365天漲跌幅",
        "2年 (730天)": "730天漲跌幅"
    }
    selected_period = st.radio("選擇統計週期", list(periods.keys()), horizontal=True)
    col_name = periods[selected_period]

    st.subheader(f"📊 各標的 {selected_period} 漲跌幅統計")
    
    # 繪製 Plotly 長條圖
    if col_name in df.columns:
        # 清理百分比字串轉換為浮點數進行繪圖
        plot_df = df.copy()
        plot_df['rate'] = plot_df[col_name].astype(str).str.rstrip('%').astype(float)
        plot_df['color'] = plot_df['rate'].apply(lambda x: '#E53935' if x < 0 else '#43A047')

        fig = px.bar(
            plot_df,
            x=plot_df.columns[1], # 標的中文名稱
            y='rate',
            text='rate',
            title=f"各資產累積報酬率 ({selected_period})",
            labels={'x': '標的', 'rate': '漲跌幅 (%)'}
        )
        fig.update_traces(marker_color=plot_df['color'], texttemplate='%{text:.2f}%', textposition='outside')
        fig.update_layout(height=450, xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    # 顯示原始資料表
    st.subheader("📋 完整市場數據明細")
    st.dataframe(df, use_container_width=True, hide_index=True)

except Exception as e:
    st.error(f"資料讀取失敗，請確認試算表共用設定：{e}")
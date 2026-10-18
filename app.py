import math
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_gsheets import GSheetsConnection

SHEET_URL = "https://docs.google.com/spreadsheets/d/1DM6wyfgrJCRYDY3vtPZtTwU3TkaPvw00FMGCnSy8Gpc/edit#gid=0"
PERIODS = {
    "近兩週": "14天漲跌幅",
    "近一個月": "30天漲跌幅",
    "近三個月": "90天漲跌幅",
    "近一年": "365天漲跌幅",
    "近兩年": "730天漲跌幅",
}
# 僅替已確認的代碼命名、分類；新增的未知標的仍保留在「其他」。
ASSETS = {
    "CURRENCY:USDTWD": ("美元／新台幣", "匯率與加密貨幣", "USDTWD"),
    "CURRENCY:BTCUSD": ("比特幣／美元", "匯率與加密貨幣", "BTCUSD"),
    "INDEXSP:.INX": ("標普 500 指數", "股票", ".INX"),
    "TPE:0050": ("臺灣 0050", "股票", "0050"),
    "VT": ("全球股票", "股票", "VT"),
    "VTI": ("美國股票", "股票", "VTI"),
    "VEA": ("已開發市場股票", "股票", "VEA"),
    "VWO": ("新興市場股票", "股票", "VWO"),
    "BND": ("美國整體債券", "債券", "BND"),
    "BNDX": ("國際債券", "債券", "BNDX"),
    "VGIT": ("美國中期公債", "債券", "VGIT"),
    "IEI": ("美國 3–7 年期公債", "債券", "IEI"),
    "XLK": ("科技類股", "股票", "XLK"),
    "VGT": ("資訊科技類股", "股票", "VGT"),
    "GOLD": ("黃金", "黃金", "GOLD"),
}
CATEGORIES = ["全部", "股票", "債券", "匯率與加密貨幣", "黃金", "其他"]


def numeric_values(values, percent=False):
    """來源 CSV 的百分比帶 %，轉成圖表使用的百分點，不猜測縮放倍率。"""
    text = values.astype("string").str.strip()
    text = text.str.replace("−", "-", regex=False).str.replace(",", "", regex=False)
    if percent:
        text = text.str.replace("％", "%", regex=False).str.removesuffix("%")
    numbers = pd.to_numeric(text, errors="coerce")
    return numbers.where(numbers.map(lambda value: pd.notna(value) and math.isfinite(value)))


def prepare_data(raw):
    if len(raw.columns) < 3:
        raise ValueError("來源缺少資產代碼、資產名稱或目前價格欄位。")
    frame = raw.copy()
    frame.columns = [str(column).strip() for column in frame.columns]
    frame = frame.rename(columns={frame.columns[0]: "資產代碼", frame.columns[1]: "來源名稱"})
    frame["資產代碼"] = frame["資產代碼"].fillna("").astype(str).str.strip()
    frame = frame.loc[frame["資產代碼"] != ""].copy()
    if "目前價格" not in frame.columns:
        raise ValueError("來源缺少「目前價格」欄位。")
    names, groups, labels = [], [], []
    for _, row in frame.iterrows():
        code = row["資產代碼"]
        original = "" if pd.isna(row["來源名稱"]) else str(row["來源名稱"]).strip()
        name, group, short_code = ASSETS.get(code, (original or code, "其他", code))
        names.append(name)
        groups.append(group)
        labels.append(f"{name}（{short_code}）" if name != short_code else name)
    frame["資產名稱"], frame["資產類型"], frame["圖表名稱"] = names, groups, labels
    frame["目前價格"] = numeric_values(frame["目前價格"])
    for column in PERIODS.values():
        if column not in frame.columns:
            frame[column] = float("nan")
        else:
            frame[column] = numeric_values(frame[column], percent=True)
    return frame


@st.cache_data(ttl=600, show_spinner=False)
def load_market_data():
    connection = st.connection("gsheets", type=GSheetsConnection)
    # 本層統一快取資料與讀取時間，避免手動更新仍命中連線層的舊快取。
    raw = connection.read(spreadsheet=SHEET_URL, worksheet="0", skiprows=2, ttl=0)
    return prepare_data(raw), datetime.now(ZoneInfo("Asia/Taipei"))


def select_data(data, category, column, order):
    selected = data if category == "全部" else data.loc[data["資產類型"] == category]
    return selected.sort_values(
        column, ascending=order == "跌幅最高優先", na_position="last", kind="stable"
    ).copy()


def make_chart(data, column):
    chart_data = data.loc[data[column].notna()].copy()
    chart_data["顏色"] = chart_data[column].map(
        lambda value: "#E53935" if value < 0 else "#43A047" if value > 0 else "#7B8794"
    )
    chart_data["漲跌幅"] = chart_data[column].map(lambda value: f"{value:+.2f}%")
    figure = px.bar(
        chart_data, x=column, y="圖表名稱", orientation="h", text="漲跌幅",
        labels={column: "漲跌幅（%）", "圖表名稱": ""},
    )
    figure.update_traces(
        marker_color=chart_data["顏色"], textposition="outside", cliponaxis=False,
        hovertemplate="%{y}<br>漲跌幅：%{x:+.2f}%<extra></extra>",
    )
    figure.update_layout(
        height=max(300, 90 + len(chart_data) * 38),
        margin=dict(l=0, r=70, t=15, b=40),
        showlegend=False, plot_bgcolor="rgba(0,0,0,0)", dragmode=False,
        font=dict(size=13),
        yaxis=dict(
            title="", categoryorder="array",
            categoryarray=chart_data["圖表名稱"].tolist(), autorange="reversed",
            automargin=True, fixedrange=True,
        ),
        xaxis=dict(
            title="漲跌幅（%）", ticksuffix="%", zeroline=True,
            zerolinecolor="#8B98A8", zerolinewidth=1, fixedrange=True,
            gridcolor="rgba(128,128,128,0.15)",
        ),
    )
    low, high = min(0, chart_data[column].min()), max(0, chart_data[column].max())
    padding = max((high - low) * 0.18, 0.5)
    figure.update_xaxes(range=[low - padding, high + padding])
    return figure


def show_details(selected, column):
    with st.expander("查看詳細數據", expanded=False):
        st.caption("依目前的資產類型與排序顯示。價格依來源計價幣別呈現；缺漏或無效值顯示「暫無資料」。")
        detail = selected[["資產名稱", "資產代碼", "資產類型", "目前價格"] + list(PERIODS.values())].copy()
        detail = detail.rename(columns={value: key for key, value in PERIODS.items()})
        display = detail.copy()
        display["目前價格"] = display["目前價格"].map(
            lambda value: "暫無資料" if pd.isna(value) else f"{value:,.4f}".rstrip("0").rstrip(".")
        )
        for period in PERIODS:
            display[period] = display[period].map(
                lambda value: "暫無資料" if pd.isna(value) else f"{value:+.2f}%"
            )
        st.dataframe(display, use_container_width=True, hide_index=True)
        missing_prices = selected.loc[selected["目前價格"].isna(), "資產名稱"]
        if not missing_prices.empty:
            st.caption("目前價格暫缺：" + "、".join(missing_prices))
        st.download_button(
            "下載目前篩選資料（CSV）",
            data=display.to_csv(index=False).encode("utf-8-sig"),
            file_name="market-data.csv", mime="text/csv", use_container_width=False,
        )


def load_news_reports():
    """Only read checked-in reports; browsing never performs news searches or generation."""
    folder = Path(__file__).resolve().parent / "news" / "weekly"
    reports = []
    for path in sorted(folder.glob("*.json"), reverse=True):
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("schema_version") != 1:
            raise ValueError("不支援的週報格式")
        start = datetime.fromisoformat(report["period_start"])
        cutoff = datetime.fromisoformat(report["cutoff"])
        if start.tzinfo is None or cutoff.tzinfo is None or cutoff <= start:
            raise ValueError("週報期間格式錯誤")
        titles = set()
        for region in ("國際", "臺灣"):
            items = report["sections"][region]
            if len(items) > 10:
                raise ValueError("每區最多列出十則新聞")
            for item in items:
                date = datetime.strptime(item["date"], "%Y-%m-%d").date()
                if not start.date() <= date <= cutoff.date():
                    raise ValueError("新聞日期超出週報期間")
                if item["title"] in titles:
                    raise ValueError("週報有重複新聞")
                titles.add(item["title"])
                for key in ("title", "summary", "impact", "topic"):
                    if not isinstance(item[key], str) or not item[key].strip():
                        raise ValueError("新聞內容不完整")
                if not item["sources"]:
                    raise ValueError("新聞缺少來源")
                for source in item["sources"]:
                    parsed = urlparse(source["url"])
                    if (parsed.scheme != "https" or not parsed.netloc
                            or any(char.isspace() for char in source["url"])):
                        raise ValueError("新聞來源連結格式錯誤")
        reports.append(report)
    return reports


def show_news():
    st.subheader("每週財經週報")
    try:
        reports = load_news_reports()
    except (ValueError, KeyError, TypeError, OSError):
        st.error("週報暫時無法載入，請稍後再試。")
        return
    if not reports:
        st.info("第一期週報準備中。")
        return
    labels = [f'{report["title"]}（{report["status"]}）' for report in reports]
    choice = st.selectbox("選擇期別", range(len(reports)), format_func=lambda i: labels[i])
    report = reports[choice]
    start = datetime.fromisoformat(report["period_start"])
    cutoff = datetime.fromisoformat(report["cutoff"])
    st.caption(f'新聞期間：{start:%Y/%m/%d %H:%M} 至 {cutoff:%Y/%m/%d %H:%M}（臺北時間）')
    st.info(report["notice"])
    st.caption("依政策、市場與產業影響篩選，同一事件合併呈現；『可能影響』為分析，並非已發生的結果。")
    region = st.radio("新聞範圍", ["國際", "臺灣"], horizontal=True)
    items = report["sections"][region]
    st.markdown(f"**{region}財經新聞 · {len(items)} 則**")
    if len(items) < 10:
        st.caption(f"本期已查證並收錄 {len(items)} 則，未滿 10 則，不以重複或無法查證的消息補足。")
    for index, item in enumerate(items, 1):
        with st.expander(f'{index:02d}. {item["title"]}（{item["date"][5:]}）'):
            st.caption(f'{item["date"]} · {item["topic"]}')
            if item.get("date_note"):
                st.caption(item["date_note"])
            st.markdown("**事件摘要**")
            st.write(item["summary"])
            st.markdown("**可能影響（分析）**")
            st.write(item["impact"])
            for source in item["sources"]:
                st.link_button(f'閱讀原文：{source["name"]}', source["url"])
    st.caption(f'本期整理時間：{report["prepared_at"]}。日期為事件或公告發布日，另有差異時個別註明。')


def main():
    st.set_page_config(
        page_title="財經小聚市場動態", layout="wide", initial_sidebar_state="collapsed"
    )
    st.markdown("""
        <style>
        #MainMenu, footer, header {visibility: hidden;}
        .block-container {max-width: 1120px; padding: 2rem 1.25rem;}
        h1 {font-size: clamp(1.5rem, 4vw, 2rem) !important;}
        div[data-testid="stRadio"] div[role="radiogroup"] {gap: .4rem;}
        div[data-testid="stRadio"] label:is([data-baseweb="radio"], [data-testid="stRadioOption"]) {
            border: 1px solid rgba(128,128,128,.3);
            border-radius: .65rem; padding: .45rem .75rem; margin: 0; min-height: 44px;
        }
        div[data-testid="stRadio"] label[data-selected="true"],
        div[data-testid="stRadio"] label:has(input:checked) {
            background: rgba(59,130,246,.12); border-color: #3b82f6;
        }
        @media (max-width: 600px) {
            .block-container {padding: 1.25rem .75rem;}
            div[data-testid="stRadio"] label:is([data-baseweb="radio"], [data-testid="stRadioOption"]) {padding: .35rem .5rem;}
        }
        </style>
    """, unsafe_allow_html=True)
    st.title("財經小聚市場動態")
    page = st.radio("內容", ["市場表現", "財經週報"], horizontal=True)
    if page == "財經週報":
        show_news()
        return
    st.caption("比較不同期間的資產表現，選擇你關心的市場。")
    if st.button("重新讀取資料", help="立即向來源重新讀取，不等待 10 分鐘快取。"):
        load_market_data.clear()
    try:
        with st.spinner("正在讀取市場資料…"):
            data, fetched_at = load_market_data()
    except Exception:
        st.error("目前無法讀取市場資料。請稍後按「重新讀取資料」，或檢查來源試算表的共用設定。")
        st.stop()
    if data.empty:
        st.info("來源目前沒有資產資料，請更新試算表後重新讀取。")
        return
    st.caption(
        f"資料讀取時間：{fetched_at:%Y/%m/%d %H:%M:%S}（臺北時間） · 快取 10 分鐘"
    )
    st.caption("來源未提供行情更新時間；讀取時間不代表報價時間，報價可能有延遲。")
    period = st.radio("統計期間", list(PERIODS), horizontal=True)
    category_col, order_col = st.columns([3, 2])
    available = [group for group in CATEGORIES if group == "全部" or group in data["資產類型"].values]
    with category_col:
        category = st.selectbox("資產類型", available)
    with order_col:
        order = st.selectbox("排列方式", ["漲幅最高優先", "跌幅最高優先"])
    column = PERIODS[period]
    selected = select_data(data, category, column, order)
    st.subheader(f"{period}資產漲跌幅")
    valid_count = int(selected[column].notna().sum())
    st.caption(f"{category} · {len(selected)} 個標的 · {valid_count} 個有漲跌幅資料 · 綠漲、紅跌")
    if valid_count:
        st.plotly_chart(make_chart(selected, column), use_container_width=True,
                        config={"displayModeBar": False, "scrollZoom": False})
    else:
        st.info("此篩選條件目前沒有可用的漲跌幅資料，可切換期間或資產類型。")
    missing = selected.loc[selected[column].isna(), "資產名稱"]
    if not missing.empty:
        st.caption("本期漲跌幅暫缺，未繪入圖表：" + "、".join(missing))
    show_details(selected, column)
    st.markdown(f"[查看來源試算表]({SHEET_URL})")


if __name__ == "__main__":
    main()

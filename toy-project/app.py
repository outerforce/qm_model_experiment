import subprocess
import sys
import time
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# ==============================================================================
# 0. 环境补丁 (自动确保依赖完整)
# ==============================================================================
try:
    import pymysql
except ImportError:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "pymysql", "cryptography"]
    )
    import pymysql

# ==============================================================================
# 1. 数据库与全局配置层 (MySQL Config)
# ==============================================================================
DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "123456",  # 👈 请修改为你本地的 MySQL 密码
    "database": "qm_portfolio",  # 👈 请修改为你本地的数据库名
    "charset": "utf8mb4",
}

# 扩展后的完整 Tickers 矩阵 (融合第一批与第二批)
TICKERS_DICT = {
    "XEQT.TO": "XEQT",
    "VFV.TO": "VFV",
    "SHOP.TO": "Canada_Tech",
    "NVDA": "AI_Hardware",
    "MU": "MU",
    "AMD": "AMD",
    "ZRE.TO": "REITs",
    "HSAV.TO": "Cash_Equiv",
    "COIN": "COIN",
    "GOOG": "Google",
    "TSLA": "Tesla",
    "GLD": "Gold_Asset",
    "SLV": "Silver_Asset",
    "TEM": "Tempus",
    "MRVL": "MRVL"
}


def init_db():
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS asset_prices (
                date DATE,
                ticker VARCHAR(20),
                close_price DECIMAL(12, 4),
                PRIMARY KEY (date, ticker)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        st.sidebar.warning(f"⚠️ 数据库未连通，已启用纯内存模式运行。")


def save_to_db(df_pivoted):
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cur = conn.cursor()
        df_long = df_pivoted.reset_index().melt(
            id_vars=["Date"], var_name="ticker", value_name="close_price"
        )
        rows = [
            (
                row["Date"].strftime("%Y-%m-%d"),
                row["ticker"],
                float(row["close_price"]),
            )
            for _, row in df_long.iterrows()
            if pd.notna(row["close_price"])
        ]
        insert_query = """
            INSERT INTO asset_prices (date, ticker, close_price)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE close_price = VALUES(close_price);
        """
        cur.executemany(insert_query, rows)
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass


# ==============================================================================
# 2. 核心数据引擎 (多模态数据获取)
# ==============================================================================


@st.cache_data(ttl=3600)
def load_historical_base(years=5):
    """【慢速持久层】获取历史日线级数据并持久化"""
    raw_data = yf.download(list(TICKERS_DICT.keys()), period=f"{years}y", interval="1d")[
        "Close"
    ]
    portfolio_df = raw_data.rename(columns=TICKERS_DICT).ffill().bfill()
    save_to_db(portfolio_df)
    return portfolio_df


def fetch_realtime_snapshot():
    """【高频实时层】实时拉取今日内最新分钟级数据 (无缓存，实时触发)"""
    # 抓取最近 1 天、粒度为 1 分钟的最热实时切片
    raw_rt = yf.download(list(TICKERS_DICT.keys()), period="1d", interval="1m")[
        "Close"
    ]
    rt_df = raw_rt.rename(columns=TICKERS_DICT).ffill().bfill()
    return rt_df


# ==============================================================================
# 3. UI 大屏展现层
# ==============================================================================
st.set_page_config(page_title="全球资产实时监控与量化看板", layout="wide")
init_db()

# 侧边栏动态控制
st.sidebar.header("⚡ 实时引擎控制面板")
enable_autorefresh = st.sidebar.toggle("开启流式数据实时轮询", value=True)
refresh_interval = st.sidebar.slider(
    "页面刷新频率 (秒)", min_value=5, max_value=60, value=15
)

st.sidebar.subheader("📐 量化回测参数")
years_selected = st.sidebar.slider(
    "回测历史深度 (年)", min_value=1, max_value=10, value=3
)
rolling_window = st.sidebar.slider(
    "滚动相关性窗口 (天数)", min_value=10, max_value=200, value=30
)

# 核心数据流组装
df_historical = load_historical_base(years=years_selected)
df_returns = df_historical.pct_change().dropna()
corr_matrix = df_returns.corr(method="pearson")

try:
    df_rt = fetch_realtime_snapshot()
    latest_prices = df_rt.iloc[-1]
    prev_prices = df_rt.iloc[0]
    rt_available = True
except Exception:
    rt_available = False

# ------------------------------------------------------------------------------
# 3.1 实时行情状态栏 (Real-time Metric Cards)
# ------------------------------------------------------------------------------
st.subheader("⏱️ 盘中分钟级实时流速快照")
if rt_available:
    # 🟢 修复：这里的字符串必须与你最新的 TICKERS_DICT 里的 Value 完全一致
    target_assets = ["COIN", "Google", "Tesla", "Gold_Asset", "MRVL"]
    
    cols = st.columns(5)
    for i, asset in enumerate(target_assets):
        with cols[i]:
            price = latest_prices[asset]
            # 计算相较于今日开盘的实时涨跌幅
            change_pct = ((price - prev_prices[asset]) / prev_prices[asset]) * 100
            st.metric(
                label=f"{asset}",
                value=f"${price:.2f}",
                delta=f"{change_pct:+.2f}%",
                delta_color="normal",
            )

# ------------------------------------------------------------------------------
# 3.2 交互标签页
# ------------------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs(
    ["📊 今日实时日内走势", "📈 长期净值对比", "🔥 静态相关性", "🌀 动态滚动相关性"]
)

with tab1:
    st.subheader("日内 1-Minute 实时流图表")
    if rt_available:
        # 归一化日内起点
        df_rt_norm = df_rt / df_rt.iloc[0]
        fig_rt = px.line(
            df_rt_norm,
            x=df_rt_norm.index,
            y=df_rt_norm.columns,
            labels={"value": "日内相对收益率", "Datetime": "时间"},
            color_discrete_sequence=px.colors.qualitative.Plotly,
        )
        fig_rt.update_layout(hovermode="x unified", height=500)
        st.plotly_chart(fig_rt, use_container_width=True)

with tab2:
    st.subheader("多资产长期历史净值曲线")
    df_normalized = df_historical / df_historical.iloc[0]
    fig_hist = px.line(df_normalized, x=df_normalized.index, y=df_normalized.columns)
    fig_hist.update_layout(hovermode="x unified", height=500)
    st.plotly_chart(fig_hist, use_container_width=True)

with tab3:
    st.subheader("全局静态皮尔逊矩阵")
    fig_heatmap = px.imshow(
        corr_matrix,
        text_auto=".2f",
        color_continuous_scale="RdBu_r",
        zmin=-1,
        zmax=1,
    )
    st.plotly_chart(fig_heatmap, use_container_width=True)

with tab4:
    st.subheader("滚动相关性瞬时观测")
    c1, c2 = st.columns(2)
    with c1:
        a1 = st.selectbox("资产 A", df_returns.columns, index=6, key="k_a1")  # 默认选新加的 COIN
    with c2:
        a2 = st.selectbox("资产 B", df_returns.columns, index=8, key="k_a2")  # 默认选新加的 TSLA

    if a1 != a2:
        rc = (
            df_returns[a1]
            .rolling(window=int(rolling_window))
            .corr(df_returns[a2])
            .dropna()
        )
        fig_rc = go.Figure()
        fig_rc.add_trace(go.Scatter(x=rc.index, y=rc.values, mode="lines", name="相关系数"))
        fig_rc.update_layout(yaxis_range=[-1.05, 1.05], hovermode="x unified")
        fig_rc.add_hline(y=0.0, line_dash="dash", line_color="gray")
        st.plotly_chart(fig_rc, use_container_width=True)

# ------------------------------------------------------------------------------
# 3.4 实时刷新引擎核心驱动器
# ------------------------------------------------------------------------------
if enable_autorefresh:
    # 在页面底部展示倒计时进度条
    placeholder = st.empty()
    for remaining in range(refresh_interval, 0, -1):
        placeholder.caption(f"🔄 正在流式监听实时市场... {remaining} 秒后触发下一次心跳同步")
        time.sleep(1)
    # 时间到，强制触发 Streamlit 重新执行本脚本
    st.rerun()
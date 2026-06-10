import pandas as pd
import yfinance as yf


def get_core_portfolio_data(years=5):
    """抓取核心资产矩阵的收盘价，并输出干净的 DataFrame"""
    # 定义第一批 Tickers
    tickers = {
        "Global_Equity": "XEQT.TO",
        "US_LargeCap": "VFV.TO",
        "AI_Hardware": "NVDA",
        "Semiconductor_Memory": "MU",
        "REITs": "ZRE.TO",
        "Cash_Equiv": "HSAV.TO",
    }

    print("🚀 开始从 Yahoo Finance 抓取数据...")

    # 下载数据 (仅提取收盘价 'Close')
    raw_data = yf.download(
        list(tickers.values()), period=f"{years}y", interval="1d"
    )["Close"]

    # 重命名列名，让它在分析时更具可读性
    reverse_mapping = {v: k for k, v in tickers.items()}
    portfolio_df = raw_data.rename(columns=reverse_mapping)

    # 🔧 数据清洗（数据分析师的必备基本功）：
    # 由于美股和加股有不同的公众假期（如加拿大的维多利亚日、美国感恩节），会导致数据出现 NaN
    # 我们采用前向填充（用前一天的价格代替），如果没有前一天则用后一天填充，确保时序连续
    portfolio_df = portfolio_df.ffill().bfill()

    print("✅ 数据清洗完成！")
    return portfolio_df


if __name__ == "__main__":
    df = get_core_portfolio_data(years=5)
    print("\n📋 数据前五行预览:")
    print(df.head())

    print("\n📊 资产基础统计描述:")
    print(df.describe())
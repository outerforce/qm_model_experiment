import pandas as pd
import yfinance as yf
tickers = ["COIN", "GOOG", "TSLA", "GLD", "CRML.TO", "MIRA.TO", "SVR-UN.TO", "XEQT.TO"]

print("🔍 开始逐个排查资产的真实最新交易日期：")
for t in tickers:
    try:
        df = yf.download(t, period="1d", interval="1m") # 查实时
        df_hist = yf.download(t, period="5y", interval="1d") # 查历史
        print(f"✅ {t:10} -> 历史最新日期: {df_hist.index[-1].strftime('%Y-%m-%d')}, 日内实时数据行数: {len(df)}")
    except Exception as e:
        print(f"❌ {t:10} -> 获取失败，报错: {e}")
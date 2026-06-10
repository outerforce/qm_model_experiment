# alert_worker.py
import time
import schedule
import yfinance as yf
import requests

TICKERS_DICT = {"COIN": "COIN", "TSLA": "Tesla", "MRVL": "MRVL"}

def check_market_anomaly():
    print("⚡ 正在执行盘中扫描...")
    try:
        # 只拉取 1 天的分钟线
        raw_rt = yf.download(list(TICKERS_DICT.keys()), period="1d", interval="1m")["Close"]
        rt_df = raw_rt.ffill().bfill()
        
        latest_prices = rt_df.iloc[-1]
        open_prices = rt_df.iloc[0]
        
        for ticker, name in TICKERS_DICT.items():
            price = latest_prices[ticker]
            change_pct = ((price - open_prices[ticker]) / open_prices[ticker]) * 100
            
            print(f"[{name}] 当前价: ${price:.2f}, 今日涨跌: {change_pct:+.2f}%")
            
            if change_pct <= -5.0:
                print(f"🚨 触发阈值！{name} 跌幅已达 {change_pct:.2f}%，正在发送警报...")
                # 在这里调用上面的请求 Webhook 发送短信/消息
                
    except Exception as e:
        print(f"扫描出错: {e}")

# 在交易时间内，每 30 秒轮询一次
schedule.every(30).seconds.do(check_market_anomaly)

if __name__ == "__main__":
    print("🚀 独立监控 Worker 已启动，正在监听盘中非正常波动...")
    while True:
        schedule.run_pending()
        time.sleep(1)
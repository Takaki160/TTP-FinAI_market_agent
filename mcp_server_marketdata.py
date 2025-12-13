from mcp.server.fastmcp import FastMCP
import yfinance as yf
import pandas as pd

mcp = FastMCP("UBS-Universal-Data-Provider")


@mcp.tool()
def fetch_asset_raw_data(symbol: str, period: str = "1mo", interval: str = "1d") -> str:
    """
    获取任何资产的历史原始行情数据
    - symbol: 代码 (如 'AAPL', 'GC=F', 'EURUSD=X')
    - period: 时间范围 ('1d', '5d', '1mo', '3mo', '1y', '5y', 'max')
    - interval: 频率 ('1d' 天, '1wk' 周, '1mo' 月)
    """
    try:
        asset = yf.Ticker(symbol)
        # 获取历史 OHLCV 数据 (Open, High, Low, Close, Volume)
        hist = asset.history(period=period, interval=interval)

        if hist.empty:
            return f"未能找到 {symbol} 的数据。"

        # 1. 基础信息
        info = asset.info
        name = info.get('longName', symbol)

        # 2. 准备数据快照 (为了节省 Token，只取日期和收盘价)
        # 我们把 DataFrame 转成 CSV 字符串，LLM 对这种结构化文本的处理能力极强
        data_snippet = hist[['Close']].reset_index()
        data_snippet['Date'] = data_snippet['Date'].dt.strftime('%Y-%m-%d')
        csv_data = data_snippet.to_csv(index=False)

        return (f"资产名称: {name} ({symbol})\n"
                f"数据时间范围: {period}\n"
                f"--- 原始价格序列 (Date, Close) ---\n"
                f"{csv_data}")

    except Exception as e:
        return f"获取数据失败: {str(e)}"


if __name__ == "__main__":
    mcp.run()
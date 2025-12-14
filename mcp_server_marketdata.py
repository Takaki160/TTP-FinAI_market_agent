from mcp.server.fastmcp import FastMCP
import yfinance as yf
import pandas as pd

# 初始化 MCP Server
mcp = FastMCP(
    name="Market-Data-Engine",
    instructions="提供股票/指数/指数期货的行情与全部指标数据"
)


@mcp.tool()
def search_assets(query: str) -> str:
    """
    通过名称搜索资产代码（Ticker）。
    当不知道具体代码（如'标普500'或'腾讯'）时，LLM 应首先调用此工具。
    """
    try:
        search = yf.Search(query, max_results=10)
        results = search.quotes
        if not results:
            return f"未找到与 '{query}' 相关的资产代码。"

        # 以表格形式输出，方便 LLM 准确识别 symbol
        df = pd.DataFrame(results)[['shortname', 'symbol', 'quoteType', 'exchange']]
        return "--- 搜索结果列表 ---\n" + df.to_string(index=False)
    except Exception as e:
        return f"搜索失败: {str(e)}"


@mcp.tool()
def get_full_asset_metrics(symbol: str) -> str:
    """
    获取资产的全部指标。
    返回该资产在 yfinance 中的完整 info 字典，包含但不限于：
    - 股票：P/E, Beta, 股息, 市值, 财务摘要等。
    - 指数：当前价格, 52周区间, 历史最高点等。
    - 期货：未平仓合约, 成交量, 合约规格等。
    """
    try:
        asset = yf.Ticker(symbol)
        info = asset.info

        if not info:
            return f"无法获取 {symbol} 的指标数据，请检查代码是否正确。"

        # 将字典转换为 Key: Value 格式的字符串
        metrics_output = "\n".join([f"{k}: {v}" for k, v in info.items()])

        return (f"--- {symbol} 全部指标报告 ---\n"
                f"资产类别: {info.get('quoteType', 'Unknown')}\n"
                f"{metrics_output}")
    except Exception as e:
        return f"获取指标异常: {str(e)}"


@mcp.tool()
def get_historical_market_data(symbol: str, period: str = "1mo", interval: str = "1d") -> str:
    """
    获取资产的完整历史行情序列。
    输出包含 Date, Open, High, Low, Close, Volume 的 CSV 格式数据。
    LLM 可根据此原始序列执行任何时间维度的量化分析。
    - period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
    - interval: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
    """
    try:
        asset = yf.Ticker(symbol)
        hist = asset.history(period=period, interval=interval)

        if hist.empty:
            return f"未能在指定周期 ({period}) 内获取到 {symbol} 的行情数据。"

        # 格式化数据
        data = hist.reset_index()
        # 确保日期格式整洁
        if 'Date' in data.columns:
            data['Date'] = data['Date'].dt.strftime('%Y-%m-%d')
        elif 'Datetime' in data.columns:
            data['Datetime'] = data['Datetime'].dt.strftime('%Y-%m-%d %H:%M')

        # 转换为简洁的 CSV 格式输出
        csv_data = data.to_csv(index=False, float_format="%.2f")

        return (f"--- {symbol} 历史行情数据 ({period}) ---\n"
                f"{csv_data}")
    except Exception as e:
        return f"行情抓取失败: {str(e)}"


if __name__ == "__main__":
    mcp.run()

# npx @modelcontextprotocol/inspector "D:\Anaconda\envs\UBS\python.exe" mcp_server_marketdata.py
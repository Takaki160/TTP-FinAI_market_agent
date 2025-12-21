from mcp.server.fastmcp import FastMCP
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import re

# --- LLM 指令配置 ---
INSTRUCTIONS = """
金融行情助手，提供个股、指数、指数期货、行业板块行情数据。
所有接口均返回 CSV 格式，包含: Date, Open, Close, High, Low, Volume, Pct。
调用规则：
1. period (周期): 格式如 "5d"(近5交易日), "20d"(近1月)。严禁使用具体日期。
2. symbol (代码):
   - 个股: 6位数字，如 "600519"。
   - 指数: 带市场前缀，如 "sh000001" (上证), "sz399006" (创业板)。
   - 指数期货: 大写品种+年月，如 "IF2406"。
   - 行业板块: 标准中文名称，如 "半导体", "酿酒行业"。若不确定名称，先调 get_sector_list。
"""

mcp = FastMCP(name="MarketData", instructions=INSTRUCTIONS)


# --- 核心处理逻辑 ---

def get_date_window(period: str) -> tuple[str, str, int]:
    """解析 period 计算时间窗口，放大回溯天数以确保交易日足够"""
    limit = int(re.match(r"(\d+)", period).group(1)) if re.match(r"\d+", period) else 10
    # 放大系数 1.8 + 10天冗余，确保覆盖假期并能计算首日涨跌幅
    lookback = int(limit * 1.8) + 10
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=lookback)
    return start_dt.strftime("%Y%m%d"), end_dt.strftime("%Y%m%d"), limit


def process_df(df: pd.DataFrame, limit: int) -> str:
    """统一清洗数据：重命名列 -> 计算涨跌幅 -> 格式化输出"""
    # 映射各接口不统一的列名
    col_map = {
        '日期': 'Date', 'date': 'Date',
        '开盘': 'Open', 'open': 'Open',
        '收盘': 'Close', 'close': 'Close',
        '最高': 'High', 'high': 'High',
        '最低': 'Low', 'low': 'Low',
        '成交量': 'Volume', 'volume': 'Volume',
        '涨跌幅': 'Pct', 'pct_chg': 'Pct'
    }
    df = df.rename(columns=col_map)

    # 统一日期格式
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')

    # 确保数值列为 float
    num_cols = ['Open', 'Close', 'High', 'Low', 'Volume']
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')

    # 补全涨跌幅 (指数/期货接口可能不返回 Pct)
    if 'Pct' not in df.columns and 'Close' in df.columns:
        df['Pct'] = df['Close'].pct_change() * 100

    # 填充 NaN (通常是第一天的 Pct)
    if 'Pct' in df.columns:
        df['Pct'] = df['Pct'].fillna(0.0)

    # 动态筛选存在的列
    target_cols = ['Date', 'Open', 'Close', 'High', 'Low', 'Volume', 'Pct']
    valid_cols = [c for c in target_cols if c in df.columns]

    # 截取数据
    if 'Date' in df.columns:
        return df[valid_cols].tail(limit).to_csv(index=False, float_format='%.2f')
    else:
        # 针对榜单类数据
        return df[valid_cols].head(limit).to_csv(index=False, float_format='%.2f')


# --- MCP 工具定义 ---

@mcp.tool()
def get_stock_daily(symbol: str, period: str = "5d") -> str:
    """获取 A股个股 历史行情。symbol: 6位数字 (e.g. 600519)"""
    symbol = re.sub(r"\D", "", symbol)
    start, end, limit = get_date_window(period)
    try:
        df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start, end_date=end, adjust="qfq")
        if df is None or df.empty: return "Error: No data found."
        return process_df(df, limit)
    except Exception as e:
        return f"Error: {str(e)}. Use correct symbol."


@mcp.tool()
def get_index_daily(symbol: str, period: str = "5d") -> str:
    """获取 A股指数 历史行情。symbol: 带前缀 (e.g. sh000001)"""
    start, end, limit = get_date_window(period)
    try:
        df = ak.stock_zh_index_daily_em(symbol=symbol)
        if df is None or df.empty: return "Error: Invalid symbol."

        # 本地日期过滤
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y%m%d')
        df = df[(df['date'] >= start) & (df['date'] <= end)].copy()

        if df.empty: return "Error: No data in period."
        return process_df(df, limit)
    except Exception as e:
        return f"Error: {str(e)}. Use correct symbol."


@mcp.tool()
def get_futures_daily(symbol: str, period: str = "5d") -> str:
    """获取 指数期货 历史行情。symbol: 大写 (e.g. IF2406)"""
    symbol = symbol.upper()
    start, end, limit = get_date_window(period)
    try:
        df = ak.futures_zh_daily_sina(symbol=symbol)
        if df is None or df.empty: return "Error: Contract invalid."

        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y%m%d')
        df = df[(df['date'] >= start) & (df['date'] <= end)].copy()

        if df.empty: return "Error: No data in period."
        return process_df(df, limit)
    except Exception as e:
        return f"Error: {str(e)}. Use correct symbol."


@mcp.tool()
def get_sector_daily(symbol: str, period: str = "5d") -> str:
    """获取 行业板块 历史行情。symbol: 标准中文名 (e.g. 半导体)"""
    start, end, limit = get_date_window(period)
    try:
        df = ak.stock_board_industry_hist_em(symbol=symbol, start_date=start, end_date=end, adjust="qfq")
        if df is None or df.empty: return f"Error: Sector '{symbol}' not found. Use get_sector_list to get the correct symbol."
        return process_df(df, limit)
    except Exception as e:
        return f"Error: {str(e)}. Use get_sector_list to get the correct symbol."


@mcp.tool()
def get_sector_list(top_n: int = 100) -> str:
    """获取当前市场板块涨幅榜，用于查找标准名称。返回: Name, Close, Pct"""
    try:
        df = ak.stock_board_industry_name_em()
        if df is None or df.empty: return "Error: List unavailable."

        rename_map = {'板块名称': 'Name', '最新价': 'Close', '涨跌幅': 'Pct'}
        df = df.rename(columns=rename_map)

        # 补全缺失列以适配通用格式
        for col in ['Open', 'High', 'Low', 'Volume']:
            df[col] = 0.0
        df['Date'] = datetime.now().strftime('%Y-%m-%d')

        df = df.sort_values(by='Pct', ascending=False)
        return df[['Name', 'Close', 'Pct', 'Volume']].head(top_n).to_csv(index=False, float_format='%.2f')
    except Exception as e:
        return f"Error: {str(e)}"


if __name__ == "__main__":
    mcp.run()

# npx @modelcontextprotocol/inspector "D:\Anaconda\envs\UBS\python.exe" mcp_server_marketdata.py
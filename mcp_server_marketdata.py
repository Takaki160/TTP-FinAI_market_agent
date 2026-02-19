import sys
import io
import re
from datetime import datetime, timedelta, timezone
import pandas as pd
import akshare as ak
from mcp.server.fastmcp import FastMCP

# --- 环境适配：强制标准输出为 UTF-8 ---
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- LLM 系统指令 ---
INSTRUCTIONS = """
金融行情助手，提供 A 股个股、指数、指数期货、行业板块、ETF 基金的历史行情、实时行情数据。
所有接口均返回 CSV 格式，历史行情均包含: Date, Open, Close, High, Low, Volume, Pct。

历史行情调用规则：
1. period (回溯时间): 格式如 "1d"(昨天)，"5d"(近5交易日)，"20d"(近1月)，默认 "5d"，严禁使用具体日期。
2. symbol (资产代码):
   - 个股: 6位数字代码，如 "600519"。
   - 指数: 小写字母交易所前缀 + 6位数字代码，如 "sh000001"。
   - 指数期货: 大写字母品种前缀 + 4位数字年月，如 "IF2406"。
   - 行业板块: 标准中文名称，如 "半导体"。若不确定名称，必须调用 get_sector_list 查询，严禁自行编造名称。
   - ETF 基金: 6位数字代码，如 "510300"。若不确定代码，必须调用 get_etf_list 查询，严禁自行编造代码。

实时行情调用规则：
1. 个股、行业板块、ETF 基金: 返回前 top_n 条，按涨跌幅排序，当 top_n 取较大值时，返回全部列表，可用于查找正确代码或名称。
2. 指数、指数期货: 返回全部列表，可用于查找正确代码。
"""

mcp = FastMCP(name="MarketData", instructions=INSTRUCTIONS)


# --- 辅助函数 ---
def get_date_window(period: str) -> tuple[str, str, int]:
    """解析 period 获取时间窗口 (start, end, limit)"""
    # 提取数字，默认为 10
    match = re.search(r"(\d+)", str(period))
    limit = int(match.group(1)) if match else 10

    # 放大回溯天数以覆盖非交易日
    lookback = int(limit * 2.0) + 15
    end_dt = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))
    start_dt = end_dt - timedelta(days=lookback)

    return start_dt.strftime("%Y%m%d"), end_dt.strftime("%Y%m%d"), limit


def process_csv(df: pd.DataFrame, limit: int) -> str:
    """通用数据清洗、排序与格式化 csv"""
    if df.empty:
        return "Info: No data found."

    df = df.copy()

    # 1. 统一列名映射
    col_map = {
        '日期': 'Date', 'date': 'Date',
        '开盘': 'Open', 'open': 'Open',
        '收盘': 'Close', 'close': 'Close', '最新价': 'Close',
        '最高': 'High', 'high': 'High',
        '最低': 'Low', 'low': 'Low',
        '成交量': 'Volume', 'volume': 'Volume',
        '涨跌幅': 'Pct', 'pct_chg': 'Pct', '涨跌幅(%)': 'Pct'
    }
    df = df.rename(columns=col_map)

    # 2. 确保日期格式统一并排序
    if 'Date' in df.columns:
        try:
            df['Date'] = pd.to_datetime(df['Date'])
            df = df.sort_values(by='Date', ascending=True)
            df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
        except Exception:
            pass

    # 3. 数值转换
    num_cols = ['Open', 'Close', 'High', 'Low', 'Volume', 'Pct']
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')

    # 4. 补全 Pct 列
    if 'Pct' not in df.columns and 'Close' in df.columns:
        df['Pct'] = df['Close'].pct_change() * 100
        df['Pct'] = df['Pct'].fillna(0.0)

    # 5. 筛选与截取
    target_cols = ['Date', 'Open', 'Close', 'High', 'Low', 'Volume', 'Pct']
    valid_cols = [c for c in target_cols if c in df.columns]

    final_df = df[valid_cols]

    # 有日期则取最后 N 条(最新)，无日期(榜单)取前 N 条
    if 'Date' in final_df.columns:
        return final_df.tail(limit).to_csv(index=False, float_format='%.2f')
    else:
        return final_df.head(limit).to_csv(index=False, float_format='%.2f')


def process_df(df: pd.DataFrame, limit: int) -> pd.DataFrame:
    """通用数据清洗、排序与格式化 dataframe"""
    if df.empty:
        return "Info: No data found."

    df = df.copy()

    # 1. 统一列名映射
    col_map = {
        '日期': 'Date', 'date': 'Date',
        '开盘': 'Open', 'open': 'Open',
        '收盘': 'Close', 'close': 'Close', '最新价': 'Close',
        '最高': 'High', 'high': 'High',
        '最低': 'Low', 'low': 'Low',
        '成交量': 'Volume', 'volume': 'Volume',
        '涨跌幅': 'Pct', 'pct_chg': 'Pct', '涨跌幅(%)': 'Pct'
    }
    df = df.rename(columns=col_map)

    # 2. 确保日期格式统一并排序
    if 'Date' in df.columns:
        try:
            df['Date'] = pd.to_datetime(df['Date'])
            df = df.sort_values(by='Date', ascending=True)
            df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
        except Exception:
            pass

    # 3. 数值转换
    num_cols = ['Open', 'Close', 'High', 'Low', 'Volume', 'Pct']
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')

    # 4. 补全 Pct 列
    if 'Pct' not in df.columns and 'Close' in df.columns:
        df['Pct'] = df['Close'].pct_change() * 100
        df['Pct'] = df['Pct'].fillna(0.0)

    # 5. 筛选与截取
    target_cols = ['Date', 'Open', 'Close', 'High', 'Low', 'Volume', 'Pct']
    valid_cols = [c for c in target_cols if c in df.columns]

    final_df = df[valid_cols]

    # 有日期则取最后 N 条(最新)，无日期(榜单)取前 N 条
    if 'Date' in final_df.columns:
        return final_df.tail(limit)
    else:
        return final_df.head(limit)


# --- 工具定义 ---
# 返回 CSV 版本，供 LLM 调用使用
@mcp.tool()
def get_stock_daily(symbol: str, period: str = "5d") -> str:
    """
    获取 A股个股 历史行情。
    symbol: 6位数字代码，如 600519。
    period (回溯时间): 格式如 "1d"(昨天)，"5d"(近5交易日)，"20d"(近1月)，默认 "5d"，严禁使用具体日期。
    """
    symbol = re.sub(r"\D", "", symbol)
    start, end, limit = get_date_window(period)
    try:
        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start,
            end_date=end,
            adjust="qfq"
        )
        return process_csv(df, limit)
    except Exception as e:
        return f"Error: {str(e)}. Check symbol validity using get_stock_list."


@mcp.tool()
def get_stock_list(top_n: int = 50) -> str:
    """
    获取 A股个股 实时行情，按涨跌幅排序，取前 top_n 支股票。
    注意：当 top_n 取 6000 以上时，返回全部股票列表，可以用于查找正确的股票代码。
    """
    try:
        df = ak.stock_zh_a_spot_em()
        if df is None or df.empty:
            return "Error: List unavailable."
        df.sort_values(by='涨跌幅', ascending=False, inplace=True)
        df = df.rename(columns={'名称': 'Name',
                                '代码': 'Symbol',
                                '最新价': 'Price',
                                '成交量': 'Volume',
                                '涨跌幅': 'Pct',
                                '市盈率-动态': 'PE'})
        df0 = df[['Name', 'Symbol', 'Price', 'Volume', 'Pct', 'PE']]
        return df0.head(top_n).to_csv(index=False, float_format='%.2f')
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def get_index_daily(symbol: str, period: str = "5d") -> str:
    """
    获取 A股指数 历史行情。
    symbol: 小写字母交易所前缀 + 6位数字代码，如 sh000001。
    period (回溯时间): 格式如 "1d"(昨天)，"5d"(近5交易日)，"20d"(近1月)，默认 "5d"，严禁使用具体日期。
    注意：symbol 交易所前缀取值范围仅限于 {"sz": "深交所", "sh": "上交所", "bj": "北交所", "csi": "中证指数"}
    """
    start, end, limit = get_date_window(period)
    try:
        df = ak.stock_zh_index_daily_em(symbol=symbol)
        if df is None or df.empty:
            return "Error: Symbol not found."

        # 本地日期过滤 (接口返回全量数据)
        df['date'] = pd.to_datetime(df['date'])
        start_dt = pd.to_datetime(start, format='%Y%m%d')
        end_dt = pd.to_datetime(end, format='%Y%m%d')
        df = df[(df['date'] >= start_dt) & (df['date'] <= end_dt)]

        return process_csv(df, limit)
    except Exception as e:
        return f"Error: {str(e)}. Check symbol validity using get_index_list."


@mcp.tool()
def get_index_list(symbol: str) -> str:
    """
    获取 A股指数 实时行情，按涨跌幅排序，可以用于查找正确的指数代码。
    symbol: 指数类型的中文名称。
    注意：symbol 取值范围仅限于 ["沪深重要指数", "上证系列指数", "深证系列指数", "指数成份", "中证系列指数"]
    """
    try:
        df = ak.stock_zh_index_spot_em(symbol=symbol)
        if df is None or df.empty:
            return "Error: List unavailable."
        df.sort_values(by='涨跌幅', ascending=False, inplace=True)
        df = df.rename(columns={'名称': 'Name',
                                '代码': 'Symbol',
                                '最新价': 'Price',
                                '成交量': 'Volume',
                                '涨跌幅': 'Pct'})
        df0 = df[['Name', 'Symbol', 'Price', 'Volume', 'Pct']]
        return df0.to_csv(index=False, float_format='%.2f')
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def get_futures_daily(symbol: str, period: str = "5d") -> str:
    """
    获取 指数期货 历史行情。
    symbol: 大写字母品种 + 4位数字年月，如 IF2512。
    period (回溯时间): 格式如 "1d"(昨天)，"5d"(近5交易日)，"20d"(近1月)，默认 "5d"，严禁使用具体日期。
    """
    symbol = symbol.upper()
    start, end, limit = get_date_window(period)
    try:
        df = ak.futures_zh_daily_sina(symbol=symbol)
        if df is None or df.empty:
            return "Error: Contract invalid or expired."

        df['date'] = pd.to_datetime(df['date'])
        start_dt = pd.to_datetime(start, format='%Y%m%d')
        end_dt = pd.to_datetime(end, format='%Y%m%d')
        df = df[(df['date'] >= start_dt) & (df['date'] <= end_dt)]

        return process_csv(df, limit)
    except Exception as e:
        return f"Error: {str(e)}. Check symbol validity using get_futures_list."


@mcp.tool()
def get_futures_list(symbol: str) -> str:
    """
    获取 指数期货 实时行情，可以用于查找正确的合约代码。
    symbol: 指数期货的中文名称。
    注意：symbol 取值范围仅限于 ["沪深300指数期货", "上证50指数期货", "中证500指数期货", "中证1000股指期货"]
    """
    try:
        df = ak.futures_zh_realtime(symbol)
        if df is None or df.empty:
            return "Error: List unavailable."
        df = df.rename(columns={'name': 'Name',
                                'symbol': 'Symbol',
                                'trade': 'Price',
                                'volume': 'Volume',
                                'changepercent': 'Pct',
                                'position': 'Position'})
        df0 = df[['Name', 'Symbol', 'Price', 'Volume', 'Pct', 'Position']]
        return df0.to_csv(index=False, float_format='%.2f')
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def get_sector_daily(symbol: str, period: str = "5d") -> str:
    """
    获取 行业板块 历史行情。
    symbol: 行业板块的中文名称，如 半导体。
    period (回溯时间): 格式如 "1d"(昨天)，"5d"(近5交易日)，"20d"(近1月)，默认 "5d"，严禁使用具体日期。
    """
    start, end, limit = get_date_window(period)
    try:
        df = ak.stock_board_industry_hist_em(
            symbol=symbol,
            start_date=start,
            end_date=end,
            period="日k",
            adjust="qfq"
        )
        return process_csv(df, limit)
    except Exception as e:
        return f"Error: Sector '{symbol}' not found. Use get_sector_list to check names."


@mcp.tool()
def get_sector_list(top_n: int = 10) -> str:
    """
    获取板块实时行情，按涨跌幅排序，取前 top_n 个板块。
    注意：当 top_n 取 100 以上时，返回全部板块列表，可以用于查找正确的板块名称。
    """
    try:
        df = ak.stock_board_industry_name_em()
        if df is None or df.empty:
            return "Error: List unavailable."
        df = df.rename(columns={'板块名称': 'Name',
                                '板块代码': 'Symbol',
                                '最新价': 'Price',
                                '涨跌幅': 'Pct',})
        df.sort_values(by='Pct', ascending=False, inplace=True)
        df0 = df[['Name', 'Symbol', 'Price', 'Pct']]
        return df0.head(top_n).to_csv(index=False, float_format='%.2f')
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def get_etf_daily(symbol: str, period: str = "5d") -> str:
    """获取 ETF 基金 历史行情。
    symbol: 6位数字代码，如 510300。
    period (回溯时间): 格式如 "1d"(昨天)，"5d"(近5交易日)，"20d"(近1月)，默认 "5d"，严禁使用具体日期。
    """
    symbol = re.sub(r"\D", "", symbol)
    start, end, limit = get_date_window(period)
    try:
        df = ak.fund_etf_hist_em(
            symbol=symbol,
            period = "daily",
            start_date = start,
            end_date = end,
            adjust = "qfq"
        )
        return process_csv(df, limit)
    except Exception as e:
        return f"Error: ETF '{symbol}' not found. Use get_etf_list to check names."


@mcp.tool()
def get_etf_list(top_n: int = 50) -> str:
    """
    获取 ETF 实时行情，按涨跌幅排序，取前 top_n 支 ETF。
    注意：当 top_n 取 1100 以上时，返回全部 ETF 列表，可以用于查找正确的 ETF 代码。
    """
    try:
        df = ak.fund_etf_spot_em()
        if df is None or df.empty:
            return "Error: List unavailable."
        df = df.rename(columns={'名称': 'Name',
                                '代码': 'Symbol',
                                '最新价': 'Price',
                                '成交量': 'Volume',
                                '涨跌幅': 'Pct',
                                'IOPV实时估值': 'IOPV',
                                '基金折价率': 'DiscountRate'})
        df.sort_values(by='Pct', ascending=False, inplace=True)
        df0 = df[['Name', 'Symbol', 'Price', 'Volume', 'Pct', 'IOPV', 'DiscountRate']]
        return df0.head(top_n).to_csv(index=False, float_format='%.2f')
    except Exception as e:
        return f"Error: {str(e)}"


if __name__ == "__main__":
    mcp.run()


# --- 内部函数 ---
# 返回 DataFrame 版本，供内部调用使用
def _fetch_index_daily(symbol: str, period: str = "5d") -> pd.DataFrame:
    start, end, limit = get_date_window(period)
    try:
        df = ak.stock_zh_index_daily_em(symbol=symbol)
        if df is None or df.empty:
            return "Error: Symbol not found."

        # 本地日期过滤 (接口返回全量数据)
        df['date'] = pd.to_datetime(df['date'])
        start_dt = pd.to_datetime(start, format='%Y%m%d')
        end_dt = pd.to_datetime(end, format='%Y%m%d')
        df = df[(df['date'] >= start_dt) & (df['date'] <= end_dt)]

        return process_df(df, limit)
    except Exception as e:
        return f"Error: {str(e)}"


def _fetch_index_list(symbol: str) -> pd.DataFrame:
    try:
        df = ak.stock_zh_index_spot_em(symbol=symbol)
        if df is None or df.empty:
            return "Error: List unavailable."
        df.sort_values(by='涨跌幅', ascending=False, inplace=True)
        df = df.rename(columns={'名称': 'Name',
                                '代码': 'Symbol',
                                '最新价': 'Price',
                                '成交量': 'Volume',
                                '涨跌幅': 'Pct'})
        df0 = df[['Name', 'Symbol', 'Price', 'Volume', 'Pct']]
        return df0
    except Exception as e:
        return f"Error: {str(e)}"


def _fetch_sector_daily(symbol: str, period: str = "5d") -> pd.DataFrame:
    start, end, limit = get_date_window(period)
    try:
        df = ak.stock_board_industry_hist_em(
            symbol=symbol,
            start_date=start,
            end_date=end,
            period="日k",
            adjust="qfq"
        )
        return process_df(df, limit)
    except Exception as e:
        return f"Error: {str(e)}"


def _fetch_sector_list(top_n: int = 60) -> pd.DataFrame:
    try:
        df = ak.stock_board_industry_name_em()
        if df is None or df.empty:
            return "Error: List unavailable."
        df = df.rename(columns={'板块名称': 'Name',
                                '板块代码': 'Symbol',
                                '最新价': 'Price',
                                '涨跌幅': 'Pct', })
        df.sort_values(by='Pct', ascending=False, inplace=True)
        df0 = df[['Name', 'Symbol', 'Price', 'Pct']]
        return df0.head(top_n)
    except Exception as e:
        return f"Error: {str(e)}"


def _fetch_etf_daily(symbol: str, period: str = "5d") -> pd.DataFrame:
    symbol = re.sub(r"\D", "", symbol)
    start, end, limit = get_date_window(period)
    try:
        df = ak.fund_etf_hist_em(
            symbol=symbol,
            period = "daily",
            start_date = start,
            end_date = end,
            adjust = "qfq"
        )
        return process_df(df, limit)
    except Exception as e:
        return f"Error: {str(e)}"


def _fetch_etf_list(top_n: int = 1100) -> pd.DataFrame:
    try:
        df = ak.fund_etf_spot_em()
        if df is None or df.empty:
            return "Error: List unavailable."
        df = df.rename(columns={'名称': 'Name',
                                '代码': 'Symbol',
                                '最新价': 'Price',
                                '成交量': 'Volume',
                                '涨跌幅': 'Pct',
                                'IOPV实时估值': 'IOPV',
                                '基金折价率': 'DiscountRate'})
        df.sort_values(by='Pct', ascending=False, inplace=True)
        df0 = df[['Name', 'Symbol', 'Price', 'Volume', 'Pct', 'IOPV', 'DiscountRate']]
        return df0.head(top_n)
    except Exception as e:
        return f"Error: {str(e)}"


# 测试命令
# npx @modelcontextprotocol/inspector "C:\Users\User\Programs\Anaconda\envs\UBS\python.exe" mcp_server_marketdata.py
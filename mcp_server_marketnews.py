from mcp.server.fastmcp import FastMCP
import akshare as ak
import pandas as pd
import re

# --- LLM 指令配置 ---
INSTRUCTIONS = """
金融新闻助手，提供个股资讯、新浪全球快讯及财联社电报。
所有接口均返回 CSV 格式，包含: Time, Title, Content。
调用规则：
1. symbol (代码): 6位数字，如 "600519" (仅 get_stock_news_em 需要)。
2. 其余接口无需参数，默认返回最新批次新闻。
"""

mcp = FastMCP(name="MarketNews", instructions=INSTRUCTIONS)


# --- 核心处理逻辑 ---

def clean_text(text: str) -> str:
    """清洗文本：去除 HTML 标签和多余空白"""
    if not isinstance(text, str): return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'[\r\n\t]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def extract_title(content: str) -> str:
    """从快讯内容提取标题 (用于新浪/财联社无标题情况)"""
    content = str(content)
    match = re.search(r'【(.*?)】', content)
    if match:
        return match.group(1)
    return clean_text(content)[:30] + "..."


def process_df(df: pd.DataFrame) -> str:
    """
    通用清洗函数。
    前提：输入的 df 必须已重命名为标准的 ['Time', 'Title', 'Content'] 列。
    """
    required = ['Time', 'Title', 'Content']
    for col in required:
        if col not in df.columns:
            return f"Error: Missing column '{col}' in source data."

    if df.empty: return "Info: No news found."

    # 1. 文本清洗
    df['Title'] = df['Title'].fillna('').apply(clean_text)
    df['Content'] = df['Content'].fillna('').apply(clean_text)

    # 2. 格式化时间 (确保统一为 YYYY-MM-DD HH:MM)
    try:
        df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
        df = df.sort_values(by='Time', ascending=False)
        df['Time'] = df['Time'].dt.strftime('%Y-%m-%d %H:%M')
    except Exception:
        pass  # 如果时间解析失败，保持原样字符串

    return df[['Time', 'Title', 'Content']].to_csv(index=False)


# --- MCP 工具定义 ---

@mcp.tool()
def get_stock_news_em(symbol: str) -> str:
    """[东方财富] 获取 A股个股 专项新闻 (默认最新100条)。symbol: 6位数字"""
    symbol = re.sub(r"\D", "", symbol)
    try:
        # 接口可能不稳定，需捕获 JSON 解析错误
        df = ak.stock_news_em(symbol=symbol)
        if df is None or df.empty: return f"Info: No news for {symbol}."

        # 映射列名
        rename_map = {'发布时间': 'Time', '新闻标题': 'Title', '新闻内容': 'Content'}
        df = df.rename(columns=rename_map)

        return process_df(df)
    except Exception as e:
        return f"Error: Source unavailable for {symbol} ({str(e)})."


@mcp.tool()
def get_rolling_news_sina() -> str:
    """[新浪财经] 获取全球财经快讯 (默认最新20条)。"""
    try:
        df = ak.stock_info_global_sina()
        if df is None or df.empty: return "Error: Service unavailable."

        # 映射列名 (新浪无标题，需生成)
        df = df.rename(columns={'时间': 'Time', '内容': 'Content'})
        df['Title'] = df['Content'].apply(extract_title)

        return process_df(df)
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def get_rolling_news_cls() -> str:
    """[财联社] 获取 A股/金融市场 极速电报 (默认最新20条)。"""
    try:
        df = ak.stock_info_global_cls(symbol="全部")
        if df is None or df.empty: return "Error: Service unavailable."

        # 合并日期时间
        if '发布日期' in df.columns and '发布时间' in df.columns:
            df['Time'] = df['发布日期'].astype(str) + ' ' + df['发布时间'].astype(str)
        elif 'time' in df.columns:
            df['Time'] = df['time']
        else:
            return "Error: Time column missing in CLS data."

        # 映射列名
        df = df.rename(columns={'标题': 'Title', '内容': 'Content'})
        if 'Title' not in df.columns:
            df['Title'] = df['Content'].apply(extract_title)

        return process_df(df)
    except Exception as e:
        return f"Error: {str(e)}"


if __name__ == "__main__":
    mcp.run()

# npx @modelcontextprotocol/inspector "D:\Anaconda\envs\UBS\python.exe" mcp_server_marketnews.py
import sys
import io
import re
from datetime import datetime, timedelta
import pandas as pd
import akshare as ak
from mcp.server.fastmcp import FastMCP

# --- 环境适配：强制标准输出为 UTF-8 ---
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- LLM 系统指令 ---
INSTRUCTIONS = """
金融新闻助手，提供以下 3 个接口的财经新闻：
1. 新浪财经 (Sina) - 默认最新 20 条，无需指定参数
2. 财联社 (CLS) - 默认最新 20 条，无需指定参数
3. 同花顺 (THS) - 默认最新 20 条，无需指定参数

获取财经新闻时必须使用全部 3 个接口，严禁遗漏，以确保信息全面。
所有接口均返回标准 CSV 格式字符串，包含列: Time, Title, Content。
如果新闻没有标题，Title 列将由内容自动生成。
"""

mcp = FastMCP(name="MarketNews", instructions=INSTRUCTIONS)


# --- 辅助函数 ---
def clean_text(text) -> str:
    """清洗文本：去除 HTML、换行符及多余空格"""
    if pd.isna(text):
        return ""
    text = str(text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'[\r\n\t]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def extract_title(content) -> str:
    """从内容提取标题 (处理无标题源)"""
    content = clean_text(content)
    # 优先提取【】内的内容
    match = re.search(r'【(.*?)】', content)
    if match:
        return match.group(1)
    # 否则截取前 30 字符
    return content[:30] + "..." if len(content) > 30 else content


def process_df(df: pd.DataFrame, limit: int = 20) -> str:
    """标准数据清洗与格式化流程"""
    # 避免 SettingWithCopyWarning
    df = df.copy()

    required_cols = ['Time', 'Title', 'Content']

    # 补全缺失列
    for col in required_cols:
        if col not in df.columns:
            df[col] = ""

    if df.empty:
        return "Info: No news found."

    # 1. 文本清洗
    df['Title'] = df['Title'].apply(clean_text)
    df['Content'] = df['Content'].apply(clean_text)

    # 2. 时间标准化 (YYYY-MM-DD HH:MM)
    try:
        df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
        df = df.dropna(subset=['Time'])
        df = df.sort_values(by='Time', ascending=False)
        df['Time'] = df['Time'].dt.strftime('%Y-%m-%d %H:%M')
    except Exception:
        pass  # 解析失败则保留原字符串

    # 3. 截取并输出 CSV
    return df[required_cols].head(limit).to_csv(index=False)


# --- 工具定义 ---
@mcp.tool()
def get_rolling_news_sina() -> str:
    """[新浪财经] 获取全球财经快讯 (最新 20 条)。"""
    try:
        df = ak.stock_info_global_sina()
        if df is None or df.empty:
            return "Error: Service unavailable."

        # 列名映射
        rename_map = {'时间': 'Time', '内容': 'Content', 'time': 'Time', 'content': 'Content'}
        df = df.rename(columns=rename_map)

        # 日期补全
        if '日期' in df.columns and 'Time' in df.columns:
            df['Time'] = df['日期'].astype(str) + " " + df['Time'].astype(str)

        # 标题生成
        df['Title'] = df['Content'].apply(extract_title)

        return process_df(df)
    except Exception as e:
        return f"Error fetching Sina news: {str(e)}"


@mcp.tool()
def get_rolling_news_cls() -> str:
    """[财联社] 获取电报快讯 (最新 20 条)。"""
    try:
        df = ak.stock_info_global_cls(symbol="全部")
        if df is None or df.empty:
            return "Error: Service unavailable."

        rename_map = {'标题': 'Title', '内容': 'Content', 'title': 'Title', 'content': 'Content'}
        df = df.rename(columns=rename_map)

        # 时间合并
        if '发布日期' in df.columns and '发布时间' in df.columns:
            df['Time'] = df['发布日期'].astype(str) + ' ' + df['发布时间'].astype(str)
        elif 'time' in df.columns:
            df['Time'] = df['time']

        # 标题兜底
        if 'Title' not in df.columns:
            df['Title'] = df['Content'].apply(extract_title)

        return process_df(df)
    except Exception as e:
        return f"Error fetching CLS news: {str(e)}"


@mcp.tool()
def get_rolling_news_ths() -> str:
    """[同花顺] 获取全球财经直播 (最新 20 条)。"""
    try:
        df = ak.stock_info_global_ths()
        if df is None or df.empty:
            return "Error: Service unavailable."

        rename_map = {'标题': 'Title', '内容': 'Content', '发布时间': 'Time'}
        df = df.rename(columns=rename_map)

        # 内容填充 (若内容为空，使用标题填充)
        if 'Title' in df.columns and 'Content' in df.columns:
            df['Content'] = df.apply(
                lambda x: x['Title'] if pd.isna(x['Content']) or x['Content'] == '' else x['Content'],
                axis=1
            )

        return process_df(df)
    except Exception as e:
        return f"Error fetching THS news: {str(e)}"


if __name__ == "__main__":
    mcp.run()


# 测试命令
# npx @modelcontextprotocol/inspector "C:\Users\User\Programs\Anaconda\envs\UBS\python.exe" mcp_server_marketnews.py
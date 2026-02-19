import sys
import io
import math
import logging
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd
from mcp.server.fastmcp import FastMCP

# --- 配置日志 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("MarketColor")

# --- 强制 UTF-8 输出 (解决 Windows 下乱码问题) ---
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- 尝试导入 MarketData ---
try:
    import mcp_server_marketdata as data_source

    logger.info("Successfully imported mcp_server_marketdata")
except ImportError:
    logger.warning("Could not import mcp_server_marketdata. Realtime features will be disabled.")
    data_source = None
except Exception as e:
    logger.error(f"Error importing data source: {e}")
    data_source = None

# --- MCP 实例 ---
mcp = FastMCP(
    name="MarketColor",
    instructions="金融情绪量化引擎。基于统计概率分布与信号一致性计算，无经验参数。"
)


# --- 1. 基础工具 ---
def _stat_normalize(z_score: float) -> float:
    """
    统计学归一化。
    使用高斯误差函数 (Error Function) 将 Z-Score 映射到概率区间 (-1, 1)。
    Z=1.0 -> 0.68 (1σ概率), Z=2.0 -> 0.95 (2σ概率)。
    替代了原有的 _tanh_norm 和 magic numbers。
    """
    return math.erf(z_score / math.sqrt(2))


def _calculate_z_score(val: float, history: pd.Series) -> float:
    """
    计算标准分 Z = (x - μ) / σ
    """
    if history.empty:
        return 0.0
    # 使用 ddof=1 计算样本标准差 (无偏估计)
    std_dev = history.std(ddof=1)
    if pd.isna(std_dev) or std_dev == 0:
        return 0.0
    return (val - history.mean()) / std_dev


# --- 2. 实时数据获取 ---
def _get_realtime_snapshot(symbol: str, asset_type: str) -> dict:
    """
    从 MarketData 的 List 接口中查找实时数据。
    """
    if not data_source:
        return None

    try:
        df_list = pd.DataFrame()

        # A. 行业板块
        if asset_type == "sector":
            df_list = data_source._fetch_sector_list(top_n=100)
            if not df_list.empty:
                matches = df_list[(df_list['Name'] == symbol) | (df_list['Symbol'] == symbol)]
                if not matches.empty:
                    rec = matches.iloc[0]
                    return {
                        "Price": float(rec['Price']),
                        "Pct": float(rec['Pct'])
                    }

        # B. 指数
        elif asset_type == "index":
            df_list = data_source._fetch_index_list(symbol="沪深重要指数")
            clean_symbol = symbol.lower().replace("sh", "").replace("sz", "").replace("bj", "").replace("csi", "")

            if not df_list.empty:
                matches = df_list[(df_list['Symbol'] == clean_symbol) | (df_list['Name'] == symbol)]
                if not matches.empty:
                    rec = matches.iloc[0]
                    return {
                        "Price": float(rec['Price']),
                        "Pct": float(rec['Pct'])
                    }

    except Exception as e:
        logger.error(f"Snapshot fetch error for {symbol}: {e}")
        return None

    return None


# --- 3. 核心分析逻辑 ---

def _internal_analyze(df_hist: pd.DataFrame, snapshot: dict, news_score: float) -> dict:
    """
    核心计算：基于统计分布的无参数融合算法。
    """
    # 统计学样本要求，建议至少 20 天
    if df_hist.empty or len(df_hist) < 20:
        return {"error": "History data insufficient (Need >20 days)"}

    # --- 1. 数据准备 (Data Preparation) ---

    # 历史切片：使用全部传入的历史数据来计算更稳定的分布
    # 计算对数收益率 (Log Returns)，使其更符合正态分布假设
    with np.errstate(divide='ignore', invalid='ignore'):
        hist_log_ret = np.log(df_hist['Close'] / df_hist['Close'].shift(1)).dropna()

    prev_close = df_hist['Close'].iloc[-1]

    # 初始化变量
    curr_price = prev_close
    real_pct = 0.0
    curr_log_ret = 0.0

    # 获取当前数据并计算收益率
    if snapshot:
        curr_price = snapshot['Price']

        # 【关键修改】直接优先读取 Snapshot 中的 Pct
        if 'Pct' in snapshot:
            real_pct = snapshot['Pct']
            # 反推对数收益率用于后续的 Z-Score 计算，保证统计有效性
            # Log Return = ln(1 + Pct/100)
            curr_log_ret = math.log(1 + real_pct / 100.0)
        else:
            # 备用逻辑：如果没有 Pct 字段（极少情况）
            if prev_close > 0:
                real_pct = (curr_price - prev_close) / prev_close * 100
                curr_log_ret = np.log(curr_price / prev_close)
    else:
        # 无快照模式（回退到0）
        curr_log_ret = 0.0
        real_pct = 0.0

    # 20日均线 (仅用于趋势描述，不影响打分)
    ma20 = df_hist['Close'].iloc[-20:].mean()

    # --- 2. 统计计算 (Statistical Calculation) ---

    # A. 计算价格 Z-Score (标准化偏离度)
    # 此时 curr_log_ret 已经包含了基于 Pct 的正确波动信息
    price_z = _calculate_z_score(curr_log_ret, hist_log_ret)

    # B. 技术面评分归一化 (Tech Score)
    # 使用误差函数映射到概率空间 (-1 ~ 1)，无人工阈值
    tech_score = _stat_normalize(price_z)

    # --- 3. 自适应权重融合 (Adaptive Fusion) ---

    # 逻辑：信号显著性 (Signal Magnitude) 决定权重。
    # 谁的绝对值大（信号更明确），就听谁的。
    sig_news = abs(news_score)
    sig_tech = abs(tech_score)

    epsilon = 1e-6  # 防止除零
    total_sig = sig_news + sig_tech + epsilon

    w_news = sig_news / total_sig
    w_tech = sig_tech / total_sig

    # 计算最终得分 (加权平均)
    final_score = (news_score * w_news) + (tech_score * w_tech)

    # --- 4. 几何置信度计算 (Geometric Confidence) ---

    # 逻辑：计算两个分数在线性空间中的距离一致性
    # 最大距离为 2 (1 - (-1))
    distance = abs(news_score - tech_score)
    normalized_dist = distance / 2.0

    # 置信度 = 1 - 归一化距离
    # 完全一致=1.0, 完全背离=0.0 (钳位到 0.1)
    confidence = max(0.1, 1.0 - normalized_dist)

    # --- 5. 输出格式化 ---

    # 使用标准差概率作为标签阈值
    # 1 Sigma (68%) -> 0.68
    # 0.5 Sigma (38%) -> 0.38

    if final_score > 0.68:
        mood = "极度乐观"
    elif final_score > 0.38:
        mood = "乐观"
    elif final_score < -0.68:
        mood = "极度恐慌"
    elif final_score < -0.38:
        mood = "悲观"
    else:
        mood = "中性"

    if confidence > 0.8:
        conf_label = "高"
    elif confidence > 0.5:
        conf_label = "中"
    else:
        conf_label = "低"

    trend_desc = "📉" if curr_price < ma20 else "📈"

    # 资产表现字符串
    asset_str = f"现价: {curr_price:.2f} {trend_desc}<br>涨跌: {real_pct:+.2f}% (Z:{price_z:.2f})"

    return {
        "sentiment_score": round(final_score, 2),
        "sentiment_label": mood,
        "confidence_score": round(confidence, 2),
        "confidence_label": conf_label,
        "asset_performance": asset_str,
        # 记录逻辑轨迹用于调试：显示概率分和动态权重
        "logic_trace": f"Tech(Prob):{tech_score:.2f} Weights(N/T):{w_news:.2f}/{w_tech:.2f}"
    }


# --- 4. 对外工具 ---

@mcp.tool()
def analyze_asset_sentiment(
        symbol: str,
        asset_type: str,
        news_score: float
) -> dict:
    """
    全自动量化市场情绪分析工具 (Statistical Model)。
    Args:
        symbol: 指数代码或标准行业名称 (如 "sh000001", "半导体")，可以通过 MarketData 获取
        asset_type: "index" | "sector"
        news_score: 新闻情绪分 (-1.0 ~ 1.0)
    """
    logger.info(f"Analyzing {asset_type}: {symbol}")

    if not data_source:
        return {"error": "MarketData module missing"}

    if asset_type not in ["index", "sector"]:
        return {"error": "Only 'index' and 'sector' are supported."}

    try:
        f_news_score = float(news_score)

        # Step 1: 获取并清洗历史数据
        if asset_type == "index":
            func_hist = data_source._fetch_index_daily
        else:
            func_hist = data_source._fetch_sector_daily

        # 获取稍长周期的数据 (e.g., 40d) 以确保剔除当天数据和节假日后仍有足够样本
        df_hist = func_hist(symbol, period="40d")

        if isinstance(df_hist, str) or not isinstance(df_hist, pd.DataFrame) or df_hist.empty:
            return {"error": f"Invalid or empty history data received: {df_hist}"}

        # 目标: 确保 df_hist 只包含到上一个交易日的数据
        try:
            # 假设df_hist的索引是pandas.DatetimeIndex
            # 使用中国时区(UTC+8)获取“今天”的日期
            today = datetime.now(timezone(timedelta(hours=8))).date()
            
            # 检查最后一条数据的日期是否是今天
            if not df_hist.empty and df_hist.index[-1].date() == today:
                # 如果是今天，则移除最后一行
                logger.info(f"Removing today's incomplete data for {symbol} to ensure statistical integrity.")
                df_hist = df_hist.iloc[:-1]
        except Exception as e:
            # 如果索引不是日期类型或发生其他错误, 记录一个警告但继续
            # 这种情况下模型结果的准确性可能会下降
            logger.warning(f"Could not clean history data for {symbol}. Technical score may be inaccurate. Reason: {e}")

        # 在清洗后再次检查数据是否充足
        if len(df_hist) < 20:
            return {"error": f"History data insufficient after cleaning (requires > 20 days), found {len(df_hist)}."}


        # Step 2: 获取实时快照
        snapshot = _get_realtime_snapshot(symbol, asset_type)

        # Step 3: 融合计算
        result = _internal_analyze(df_hist, snapshot, f_news_score)

        if "error" not in result:
            result["symbol"] = symbol

        return result

    except Exception as e:
        logger.error(f"Analysis tool error: {e}", exc_info=True)
        return {"error": f"Analysis failed: {str(e)}"}


if __name__ == "__main__":
    mcp.run()

# 测试命令
# npx @modelcontextprotocol/inspector "C:\Users\User\Programs\Anaconda\envs\UBS\python.exe" mcp_server_marketcolor.py
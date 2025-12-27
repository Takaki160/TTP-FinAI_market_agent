import sys
import io
import logging
from mcp.server.fastmcp import FastMCP

# --- 初始化配置 ---
# 强制 UTF-8 编码，防止中文在部分环境乱码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 配置日志输出到 stderr，严禁污染 stdout (MCP 通信通道)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("MarketColor")

mcp = FastMCP(
    name="MarketColor",
    instructions="金融市场情绪量化计算引擎。仅用于执行数学模型计算，不产生主观建议。"
)


# --- 辅助函数 ---

def _clip(val: float, low: float, high: float) -> float:
    return max(low, min(val, high))


# --- 工具定义 ---

@mcp.tool()
def calculate_sentiment_score(
        macro_score: float,
        macro_weight: float,
        sector_score: float,
        sector_weight: float
) -> dict:
    """
    计算加权市场情绪分数。

    Args:
        macro_score: 宏观维度得分 [-1.0, 1.0]
        macro_weight: 宏观权重 [0.0, 1.0]
        sector_score: 行业维度得分 [-1.0, 1.0]
        sector_weight: 行业权重 [0.0, 1.0]
    """
    # 输入防御处理
    m_score = _clip(macro_score, -1.0, 1.0)
    s_score = _clip(sector_score, -1.0, 1.0)
    m_weight = max(0.0, macro_weight)
    s_weight = max(0.0, sector_weight)

    total_weight = m_weight + s_weight
    if total_weight <= 0:
        return {"error": "Total weight must be positive", "status": "failed"}

    # 加权计算
    w_macro = m_weight / total_weight
    w_sector = s_weight / total_weight
    final_score = (m_score * w_macro) + (s_score * w_sector)

    # 情绪定性
    if final_score >= 0.6:
        mood = "Greed (极度乐观)"
    elif final_score >= 0.2:
        mood = "Optimism (乐观)"
    elif final_score <= -0.6:
        mood = "Fear (极度恐慌)"
    elif final_score <= -0.2:
        mood = "Pessimism (悲观)"
    else:
        mood = "Neutral (中性)"

    # 记录日志 (stderr)
    logger.info(f"[Sentiment] Score: {final_score:.4f} | Mood: {mood}")

    return {
        "score": round(final_score, 4),
        "mood": mood,
        "details": f"Macro({m_score}*{w_macro:.2f}) + Sector({s_score}*{w_sector:.2f})"
    }


@mcp.tool()
def calculate_confidence_level(
        news_sentiment_dir: int,
        market_price_dir: int,
        is_high_volume: bool,
        source_consensus: bool
) -> dict:
    """
    基于量价验证逻辑计算信号置信度 (0.0 - 1.0)。

    Args:
        news_sentiment_dir: 新闻方向 (1:利好, -1:利空, 0:中性)
        market_price_dir: 价格方向 (1:涨, -1:跌, 0:震荡)
        is_high_volume: 是否放量
        source_consensus: 多源是否一致
    """
    confidence = 0.5
    factors = []

    # 1. 来源一致性
    if source_consensus:
        confidence += 0.2
        factors.append("Consensus(+0.2)")

    # 2. 价格印证 (背离扣分重于一致加分)
    if news_sentiment_dir != 0:
        if news_sentiment_dir == market_price_dir:
            confidence += 0.2
            factors.append("Price_Match(+0.2)")
        elif market_price_dir != 0 and news_sentiment_dir != market_price_dir:
            confidence -= 0.3
            factors.append("Price_Divergence(-0.3)")

    # 3. 量能确认
    if is_high_volume:
        confidence += 0.1
        factors.append("High_Vol(+0.1)")
    else:
        confidence -= 0.1
        factors.append("Low_Vol(-0.1)")

    final_conf = _clip(confidence, 0.0, 1.0)

    logger.info(f"[Confidence] Level: {final_conf:.2f} | Factors: {factors}")

    return {
        "confidence": round(final_conf, 2),
        "logic_trace": " | ".join(factors)
    }


if __name__ == "__main__":
    mcp.run()
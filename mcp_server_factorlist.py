import sys
import io
import math
import logging
import pandas as pd
import numpy as np
from mcp.server.fastmcp import FastMCP

# --- 配置日志 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("RiskEngine")

# --- 强制 UTF-8 输出 ---
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- 尝试导入数据源 ---
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
    name="RiskEngine",
    instructions="金融因子风险计算引擎。负责计算市值偏好(Size)、波动率(Volatility)及均值回归预期。"
)

# --- 常量配置 ---
PROXIES = {
    "Size_Small": "sh000852",  # 中证1000
    "Size_Large": "sh000300",  # 沪深300
    "Market": "sh000001"  # 上证指数
}


# --- 1. 基础计算工具 ---

def _calculate_metrics(df: pd.DataFrame) -> dict:
    """
    计算核心量化指标：
    1. pct: 区间涨跌幅
    2. vol: 年化波动率
    3. exp_ret: 均值回归预期 (基于20日均线)
    """
    if df is None or df.empty or len(df) < 20:
        return {"pct": 0.0, "vol": 0.0, "exp_ret": 0.0}

    try:
        price_now = float(df['Close'].iloc[-1])
        price_prev = float(df['Close'].iloc[0])

        # 1. 区间涨跌幅
        pct_change = (price_now - price_prev) / price_prev * 100

        # 2. 年化波动率
        if 'Pct' in df.columns:
            annual_vol = df['Pct'].std() * math.sqrt(252)
        else:
            log_ret = np.log(df['Close'] / df['Close'].shift(1))
            annual_vol = log_ret.std() * math.sqrt(252) * 100

        # 3. 均值回归预期
        # 逻辑: (均线 - 现价) / 现价
        ma20 = df['Close'].mean()
        implied_reversion = (ma20 - price_now) / price_now * 100

        return {
            "pct": pct_change,
            "vol": annual_vol,
            "exp_ret": implied_reversion
        }

    except Exception as e:
        logger.error(f"Error calculating metrics: {e}")
        return {"pct": 0.0, "vol": 0.0, "exp_ret": 0.0}


# --- 2. 核心分析逻辑 ---

def _internal_analyze_size(window: str = "20d") -> dict:
    """分析市值因子 (Size Factor)"""
    if not data_source: return {"error": "Data module missing"}

    df_small = data_source._fetch_index_daily(PROXIES["Size_Small"], period=window)
    df_large = data_source._fetch_index_daily(PROXIES["Size_Large"], period=window)

    if isinstance(df_small, str) or df_small.empty or isinstance(df_large, str) or df_large.empty:
        return {"error": "Data unavailable"}

    m_small = _calculate_metrics(df_small)
    m_large = _calculate_metrics(df_large)

    # 计算超额收益 (Alpha)
    alpha = m_small["pct"] - m_large["pct"]

    # 状态判定
    if alpha > 3.0:
        state = "小盘显著占优"
    elif alpha < -3.0:
        state = "大盘显著占优"
    else:
        state = "风格均衡"

    return {
        "factor": "Size (市值)",
        "state_summary": state,
        "metrics": {
            "current_alpha": f"{alpha:+.2f}%",
            "small_cap_ret": f"{m_small['pct']:+.2f}%",
            "large_cap_ret": f"{m_large['pct']:+.2f}%",
            "expected_reversion": f"{m_small['exp_ret']:+.2f}%"
        }
    }


def _internal_analyze_volatility(window_long: int = 60) -> dict:
    """分析波动率因子 (Volatility)"""
    if not data_source: return {"error": "Data module missing"}

    df_market = data_source._fetch_index_daily(PROXIES["Market"], period=f"{window_long}d")

    if isinstance(df_market, str) or df_market.empty:
        return {"error": "Data unavailable"}

    # 取最近20天计算当前状态
    df_curr = df_market.iloc[-20:]
    m = _calculate_metrics(df_curr)

    state = "高波动" if m['vol'] > 20 else "低波动"

    return {
        "factor": "Volatility (波动率)",
        "state_summary": state,
        "metrics": {
            "current_vol": f"{m['vol']:.2f}%",
            "trend": state
        }
    }


# --- 3. 对外工具 ---

@mcp.tool()
def get_factor_state(factor_name: str) -> dict:
    """
    获取指定因子的量化指标（含当前收益与预期回归）。
    Args:
        factor_name: "Size" | "Volatility"
    """
    logger.info(f"Calculating factor state for: {factor_name}")
    try:
        if factor_name == "Size":
            return _internal_analyze_size()
        elif factor_name == "Volatility":
            return _internal_analyze_volatility()
        else:
            return {"error": "Unknown factor. Supported: ['Size', 'Volatility']"}
    except Exception as e:
        logger.error(f"Calculation failed: {e}")
        return {"error": str(e)}


if __name__ == "__main__":
    mcp.run()

# 测试命令
# npx @modelcontextprotocol/inspector "D:/Anaconda/envs/UBS/python.exe" mcp_server_factorlist.py

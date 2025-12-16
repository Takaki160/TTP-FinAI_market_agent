# -*- coding: utf-8 -*-
import pandas as pd
from datetime import datetime
from WindPy import w
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="Wind_Terminal_Analyst",
    instructions="""你是一个连接到 Wind 金融终端的专业分析师。
    你可以查询 A 股、港股、海外股的历史行情、财务指标和指数成分。
    当用户询问股价走势、市值对比或板块成员时，请调用相应工具。"""
)

def ensure_wind():
    if not w.isconnected():
        res = w.start()
        if res.ErrorCode != 0:
            return False, f"Wind 启动失败，错误码: {res.ErrorCode}"
    return True, "Success"

@mcp.tool()
def get_historical_market_data(symbol: str, days: int = 15) -> str:
    """
    获取指定股票的历史 K 线数据。
    :param symbol: 股票代码，如 '600519.SH' (茅台) 或 '000001.SZ' (平安银行)
    :param days: 回溯的天数，默认为最近 15 个交易日
    """
    ok, msg = ensure_wind()
    if not ok: return msg
    
    end_date = datetime.now().strftime("%Y-%m-%d")
    res = w.wsd(symbol, "open,high,low,close,volume", f"-{days}D", end_date, "PriceAdj=F", usedf=True)
    
    if res[0] == 0:
        df = res[1]
        if df.empty:
            return f"未能获取到 {symbol} 的历史数据，请检查代码或日期。"
        return f"股票 {symbol} 过去 {days} 天的历史数据 (前复权):\n{df.to_string()}"
    return f"Wind WSD 查询失败，错误码: {res[0]}"

@mcp.tool()
def get_valuation_and_info(symbols: str) -> str:
    """
    获取一个或多个股票的最新截面数据，如名称、市盈率 PE(TTM) 和总市值。
    :param symbols: 股票代码字符串，多个用逗号隔开，如 '600519.SH,000001.SZ'
    """
    ok, msg = ensure_wind()
    if not ok: return msg

    today = datetime.now().strftime("%Y-%m-%d")
    fields = "sec_name,pe_ttm,mkt_cap_ard"
    options = f"tradeDate={today}"
    
    res = w.wss(symbols, fields, options, usedf=True)
    
    if res[0] == 0:
        df = res[1]
        return f"日期 {today} 的财务截面数据：\n{df.to_string()}"
    return f"Wind WSS 查询失败，错误码: {res[0]}"

@mcp.tool()
def get_index_members(index_code: str) -> str:
    """
    获取指定指数或板块的所有成分股代码和名称。
    :param index_code: 指数代码，如 '000300.SH' (沪深300), '000001.SH' (上证指数)
    """
    ok, msg = ensure_wind()
    if not ok: return msg
    
    today = datetime.now().strftime("%Y-%m-%d")
    res = w.wset("sectorconstituent", f"date={today};windcode={index_code}", usedf=True)
    
    if res[0] == 0:
        df = res[1]
        df_display = df[['wind_code', 'sec_name']].head(50)
        total_count = len(df)
        return f"指数 {index_code} 共有 {total_count} 只成分股，前 50 只如下：\n{df_display.to_string(index=False)}"
    return f"Wind WSET 查询失败，错误码: {res[0]}"

if __name__ == "__main__":
    mcp.run()
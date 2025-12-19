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

@mcp.tool()
def get_futures_contract_chain(
    product_code: str,
    startdate: str = "",
    enddate: str = ""
) -> str:
    """
    获取指定期货品种在给定时间区间内的期货合约列表（期货合约链）。

    :param product_code: Wind 期货品种代码，例如：
        - A.DCE   黄大豆1号
        - IF.CFE  沪深300股指期货
        - RB.SHF  螺纹钢
    :param startdate: 开始日期 YYYYMMDD，默认为今天
    :param enddate: 结束日期 YYYYMMDD，默认为一年后
    """
    ok, msg = ensure_wind()
    if not ok:
        return msg

    today = datetime.now()
    if not startdate:
        startdate = today.strftime("%Y%m%d")
    if not enddate:
        enddate = today.replace(year=today.year + 1).strftime("%Y%m%d")

    params = (
        f"startdate={startdate};"
        f"enddate={enddate};"
        f"wind_code={product_code};"
    )

    res = w.wset("futurecc", params, usedf=True)

    if res[0] != 0:
        return f"Wind WSET(futurecc) 查询失败，错误码: {res[0]}"

    df = res[1]
    if df is None or df.empty:
        return f"未获取到 {product_code} 的期货合约链数据"

    cols = [
        "sec_name",
        "wind_code",
        "delivery_month",
        "contract_issue_date",
        "last_trade_date",
        "last_delivery_month",
        "change_limit",
        "target_margin",
    ]
    show_cols = [c for c in cols if c in df.columns]
    df_show = df[show_cols]

    return (
        f"期货品种 {product_code} 在 {startdate} ~ {enddate} 的合约链如下（共 {len(df)} 条）：\n"
        f"{df_show.to_string(index=False)}"
    )

@mcp.tool()
def get_futures_snapshot(symbols: str, timeout_sec: int = 1) -> str:
    """
    获取一个或多个期货合约的最新快照行情。

    说明：
    :param symbols: 期货合约代码字符串，多个用逗号分隔，例如：
        - IF2503.CFE,IH2503.CFE
    :param timeout_sec: 等待 WSQ 推送的超时秒数（默认 5 秒）
    """
    ok, msg = ensure_wind()
    if not ok:
        return msg

    codes = ",".join([s.strip() for s in symbols.split(",") if s.strip()])
    if not codes:
        return "symbols 不能为空"

    # 实时字段集合（可按需增减）
    wsq_fields = "rt_last,rt_pre_close,rt_chg,rt_pct_chg,rt_vol,rt_oi,rt_open,rt_high,rt_low"

    evt = threading.Event()
    captured = {"indata": None, "err": None}

    def _cb(indata):
        # 仅捕获第一条推送
        if captured["indata"] is None:
            captured["indata"] = indata
            evt.set()

    # 1) 优先：WSQ 订阅并等待第一条推送
    try:
        req = w.wsq(codes, wsq_fields, func=_cb)
        # 等待推送
        evt.wait(timeout=max(1, int(timeout_sec)))

        if captured["indata"] is not None:
            indata = captured["indata"]
            # indata 的结构通常为 Codes / Fields / Data
            try:
                # 将 Data 转成更易读的表格
                df = pd.DataFrame(indata.Data, index=indata.Fields).T
                df.index = indata.Codes
                return (
                    "WSQ 订阅已收到推送（实时快照）：\n"
                    f"{df.to_string()}"
                )
            except Exception:
                return f"WSQ 订阅已收到推送（原始数据）：\n{indata}"

        # 尝试取消订阅（不同 WindPy 版本方法名可能不同，尽量容错）
        try:
            if hasattr(w, "cancelRequest"):
                w.cancelRequest(req)
            elif hasattr(w, "cancel"):
                w.cancel(req)
        except Exception:
            pass

    except Exception as e:
        captured["err"] = str(e)

    # 2) 如果 WSQ 未收到推送：回退到 WSS 静态字段（非实时）
    # 对期货更常用的静态字段包括 pre_settle/settle/oi 等；并且在非交易时段建议显式指定 tradeDate 为最近交易日。
    static_fields = "sec_name,pre_close,pre_settle,close,settle,chg,pct_chg,volume,oi,open,high,low"

    # 计算最近交易日（尽量用 Wind 交易日历）
    try:
        today_str = datetime.now().strftime("%Y-%m-%d")
        td = w.tdaysoffset(0, today_str, "", usedf=True)
        # td[1] 是 DataFrame，第一行第一列是最近交易日
        trade_date = td[1].iloc[0, 0].strftime("%Y%m%d")
    except Exception:
        trade_date = datetime.now().strftime("%Y%m%d")

    res3 = w.wss(codes, static_fields, f"tradeDate={trade_date}", usedf=True)
    if res3[0] == 0:
        df3 = res3[1]
        if df3 is None or df3.empty:
            return (
                "WSQ 在超时内未收到推送，且 WSS 静态字段也无数据。\n"
                f"请检查合约代码/权限：{codes}"
            )
        extra = f"\n（WSQ 等待超时 {timeout_sec}s 未收到推送）"
        if captured["err"]:
            extra += f"\n（WSQ 调用异常：{captured['err']}）"
        return "已返回 WSS 静态字段（非实时）：\n" + df3.to_string() + extra + f"\n（tradeDate={trade_date}）"

    # 3) 最后：给出更可操作的错误信息
    detail = f"WSQ 在超时内未收到推送（{timeout_sec}s）。"
    if captured["err"]:
        detail += f" WSQ 调用异常：{captured['err']}。"
    detail += f" WSS 静态字段错误码：{res3[0]}。"
    return (
        "获取期货快照失败。\n"
        + detail
        + "\n建议：1）确认当前为交易时段；2）确认 Wind 终端已登录并且 WSQ 面板能看到该合约跳价；"
          "3）确认合约代码为活跃合约（可先用 get_futures_contract_chain 查询）。"
    )

if __name__ == "__main__":

    mcp.run()


# AI-Powered Market Intelligence

**A Financial Intelligence Agent powered by Gemini & Model Context Protocol (MCP)**

## Project Overview

本项目是一个面向 Risk Manager 和 Trader 的智能辅助系统。它不只是简单的新闻摘要工具，而是致力于构建一个**语义-因子映射层 (Semantic-Factor Mapping Layer)**。

系统利用 **Google Gemini** 的推理能力，结合 **Model Context Protocol (MCP)** 架构，实时连接市场数据与新闻流，将定性的市场情绪（Market Color）转化为定量的风险指标（Risk Indicators），如情绪得分、因子偏度预测和波动率预警。

### 核心价值

* **From Text to Metric:** 将 "谣言驱动上涨" 转化为 "Low Confidence, High Reversal Risk"。
* **Asset Coverage:** 优先覆盖 **A股股票、核心指数 (CSI300/CSI500) 及 指数期货 (IF/IC/IM)**。
* **Architecture:** 基于微服务化的 MCP 架构，解耦 LLM 与数据源。

---

## System Architecture

本项目基于 **Model Context Protocol (MCP)** 标准构建，确保数据源的可扩展性。

![img.png](img.png)

* **LLM Provider:** Google Gemini (via LangChain/LangGraph) - 负责逻辑推理与语义分析。
* **Orchestrator:** LangGraph - 管理多轮对话状态与工具调用链。
* **MCP Client:** 负责与各数据服务通信。
* **MCP Servers:**
* `mcp-server-market`: 获取行情数据 (Price, Volume, OI) - 覆盖股票/期货。
* `mcp-server-news`: 获取实时财经新闻与公告。
* `mcp-server-position`: 管理模拟持仓与风险敞口。



---

## Project Roadmap & Delivery Timeline

### Phase 1: Infrastructure & Data connectivity (Dec 21)

* **目标:** 完成基础架构搭建。部署 MCP Server 以连接 Gemini 与市场行情及新闻数据源。
* **User Visibility:**
  * **User:** “给我最近大盘走势以及重要财经新闻。”
  * **Agent:** 准确返回相关行情数据以及原始财经新闻列表。

### Phase 2: Market Color & Measurable Indicators (Dec 25)

* **目标:** 落地 **场景 A (Market Color)**。将定性的新闻转化为**可度量的指标** (情绪分数、置信度)。
* **User Visibility:**
  * **User:** “给我今天的市场情绪摘要。”
  * **Agent:**
    * “**宏观:** 新闻总结 xxx (Sentiment Score: xx, Confidence Level: xx)”
    * “**板块:** 新闻总结 xxx (Sentiment Score: xx, Confidence Level: xx)”

### Phase 3: Factor "Watchlist" & Risk Logic (Dec 28)

* **目标:** 落地 **场景 B (Factor Watchlist)**。重点在于将新闻事件映射到 **风险因子** (如动量、规模、波动率)。
* **User Visibility:**
  * **User:** “根据市场情绪，给我今天的因子观察清单 (Factor Watchlist) ”
  * **Agent:**
    * “**动量因子 (Momentum):** 风险: xxx, 预期: 因子收益 xx”
    * “**市值因子 (Size):** 风险: xxx, 预期: 因子收益 xx”
    * “**波动率因子 (Volatility):** 风险: xxx, 预期: 因子收益 xx”

### Phase 4: Final Polish & Dashboard (Dec 30)

* **目标:** 接入持仓数据，提供风险建议与相关指标的可视化展示。
* **User Visibility:**
  * **User:** “根据目前我的持仓情况，有哪些风险点？”
  * **Agent:**
    * “**风险:** xxx”
    * “**建议:** xxx”

---

## Tech Stack

* **Language:** Python 3.10+
* **LLM:** Google Gemini
* **Frameworks:**
* `langchain` / `langgraph`: Agent orchestration.
* `mcp`: Model Context Protocol implementation.


* **Data Sources (MCP Servers):**
* *AkShare / Wind API* (Market Data & News)


* **UI:** Streamlit
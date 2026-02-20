# FinAI Market Agent: 基于 MCP 的金融量化感知智能体

本项目是一个基于 **Model Context Protocol (MCP)** 和 **LangGraph** 构建的金融量化分析系统。它模拟了高级分析师的思维模式，结合实时行情、财经新闻以及统计学模型，对 A 股市场（指数、板块、个股）进行量化情绪分析。

## 1. 系统架构与模块

系统由一个中心化的 `Client` 和四个功能解耦的 `MCP Server` 组成：

*   **`client.py`**: 基于 LangGraph 编排。实现“快慢系统”逻辑，根据任务复杂度自动选择执行流。
*   **`mcp_server_marketdata.py`**: 数据中台。对接 AkShare，提供清洗后的标准化行情 CSV 数据。
*   **`mcp_server_marketnews.py`**: 情报中心。实时抓取新浪、财联社、同花顺的三大源滚动快讯。
*   **`mcp_server_marketcolor.py`**: 核心计算引擎。实现新闻情感与技术分布的量化融合算法。
*   **`mcp_server_reasoning.py`**: 认知引擎。强制 Agent 在执行复杂分析前输出思维链 (CoT)。

---

## 2. 核心量化逻辑 (MarketColor Engine)

本项目的核心在于 `analyze_asset_sentiment` 工具。它摒弃了简单的关键词匹配，采用概率论方法处理“市场色彩”：

### 2.1 技术面偏离度建模 ($S_{tech}$)
系统获取目标资产过去 30 个交易日的对数收益率分布，计算当前实时价格在历史分布中的位置：

1.  **Z-Score 计算**:
    $$Z = \frac{x_{current} - \mu_{30d}}{\sigma_{30d}}$$
    其中 $x$ 为最新价，$\mu$ 为 30 日均价，$\sigma$ 为标准差。

2.  **概率映射 (Gaussian Error Function)**:
    使用高斯误差函数将 Z-Score 映射到 $[-1, 1]$ 的概率空间，作为技术面情绪分：
    $$S_{tech} = \text{erf}\left(\frac{Z}{\sqrt{2}}\right)$$
    *注：若 $S_{tech} > 0.8$ 视为严重超买（超前情绪），$S_{tech} < -0.8$ 视为严重超跌。*

### 2.2 舆情情感评分 ($S_{news}$)
由 LLM (Gemini 2.5) 对实时抓取的滚动新闻进行语义分析，给出 $[-1, 1]$ 的情感强度得分。若处于消息真空期，则 $S_{news} = 0$。

### 2.3 动态权重融合与置信度校准
系统根据信号的显著性（绝对值大小）自动分配权重：

1.  **自适应权重 ($W$)**:
    $$W_{news} = \frac{|S_{news}|}{|S_{news}| + |S_{tech}|}, \quad W_{tech} = 1 - W_{news}$$

2.  **最终情绪得分 ($Score_{final}$)**:
    $$Score_{final} = S_{news} \cdot W_{news} + S_{tech} \cdot W_{tech}$$

3.  **几何置信度 ($Confidence$)**:
    计算新闻分与技术分的线性距离。距离越小（信号一致性越高），置信度越高。若两者发生背离（如“利好不涨”），置信度将大幅下降，触发“情绪分歧”预警。

---

## 3. 工作流：双系统处理机制

在 `client.py` 中，AI 代理根据输入指令的深度执行不同逻辑：

*   **Function 1 (基础数据查询)**:
    直接调用 `MarketData` 获取行情或 `MarketNews` 获取快讯。不进行二次加工，保持客观数据呈现。
*   **Function 2 (市场色彩量化分析)**:
    1.  调用 `ReasoningEngine` 制定取数策略。
    2.  并发获取相关指数、行业板块行情及全网快讯。
    3.  执行 `analyze_asset_sentiment` 量化计算。
    4.  输出包含“驱动力拆解 (Logic Trace)”的结构化报告，明确区分当前情绪是由**新闻驱动**还是**技术面超跌反弹**主导。

---

## 4. 部署与调试

### 依赖安装
```bash
pip install mcp langchain-google-genai langgraph pandas akshare numpy scipy
```

### 运行
1.  配置环境变量：`export GOOGLE_API_KEY="your_api_key"`
2.  执行客户端：`python client.py`

### 开发者调试
利用标准 MCP Inspector 调试单个服务端（以行情服务为例）：
```bash
npx @modelcontextprotocol/inspector python mcp_server_marketdata.py
```

---

## 5. 免责声明

1.  **数据滞后性**: 行情源于 AkShare 互联网接口，可能存在 1-5 分钟延迟。
2.  **模型局限性**: 情感分析基于 LLM 语义理解，量化分值仅作为统计参考。
3.  **风险提示**: 本工具产出报告不构成任何投资建议，金融市场操作风险自担。

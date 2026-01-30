
---

# AI Quantitative Market Agent

这是一个基于 **Model Context Protocol (MCP)** 和 **LangGraph** 构建的金融量化分析智能体。它模拟了高级分析师的思维模式，结合了**实时行情数据**、**滚动财经新闻**以及**统计学量化模型**，能够对 A 股市场（指数、板块、个股）进行量化情绪分析。

## 核心特性

* **双系统思维架构 (Dual-System Thinking)**
* **Fast System (快直觉)**: 针对简单的行情查询，直接调用数据工具快速响应。
* **Slow System (慢逻辑)**: 针对复杂的市场分析，利用 `ReasoningEngine` 进行思维链 (CoT) 规划，再执行多步取数和计算。


* **MCP 模块化设计**: 所有功能（数据、新闻、计算、推理）均封装为独立的 MCP Server，通过标准协议与 Client 通信，具备极高的扩展性和解耦性。
* **混合量化模型 (Hybrid Sentiment Engine)**: 独创的 `MarketColor` 引擎，将 LLM 对新闻的**语义打分**与基于价格分布的**技术打分**（Z-Score/Error Function）进行加权融合。
* **全维数据覆盖**:
* **行情**: A股个股、指数、期货、行业板块、ETF (数据源: AkShare)。
* **新闻**: 聚合新浪财经、财联社、同花顺三大主流财经通讯社的实时滚动新闻。



## 系统架构

系统由一个中心化的 `Client` (LangGraph Agent) 和四个独立的 `MCP Server` 组成：

```mermaid
graph TD
    User[用户指令] --> Client[LangGraph Client (Gemini-2.5)]
    
    subgraph "MCP Servers (工具层)"
        Client <-->|Stdio| MarketData[MarketData Server]
        Client <-->|Stdio| MarketNews[MarketNews Server]
        Client <-->|Stdio| MarketColor[MarketColor Server]
        Client <-->|Stdio| Reasoning[Reasoning Server]
    end
    
    MarketData -->|AkShare API| Web[互联网数据源]
    MarketNews -->|AkShare API| Web
    MarketColor -.->|Import| MarketData
```

### 模块详解

| 模块文件 | 功能描述 | 关键技术/工具 |
| --- | --- | --- |
| **`client.py`** | **大脑与编排层**。负责连接所有 MCP 服务，管理对话状态，根据 Prompt 决定调用哪些工具，并生成最终报告。 | `LangGraph`, `LangChain`, `Gemini API` |
| **`mcp_server_marketdata.py`** | **基础数据层**。提供清洗过的标准化行情数据 (CSV格式)。支持历史回溯和实时榜单。 | `AkShare`, `Pandas` |
| **`mcp_server_marketnews.py`** | **情报层**。实时抓取三大财经源的快讯，清洗 HTML 标签并统一时间格式。 | `AkShare` (Sina/CLS/THS) |
| **`mcp_server_marketcolor.py`** | **量化计算层**。执行无参数的情绪/技术融合算法。计算 Z-Score、置信度及最终情绪分。 | `NumPy`, `SciPy` |
| **`mcp_server_reasoning.py`** | **认知层**。提供 `think_and_plan` 工具，强迫 Agent 在行动前输出思维过程。 | `Chain of Thought` |

## 核心算法：MarketColor 引擎

该项目的核心亮点在于 `analyze_asset_sentiment` 工具，它摒弃了传统的硬阈值判断，采用概率论方法：

1. **文本情感 (Text Sentiment)**: LLM 阅读实时新闻并打分 。
2. **技术分布 (Technical Distribution)**:
* 获取资产过去 30 天的对数收益率分布。
* 计算当前实时价格的标准化得分$Z = \frac{x - \mu}{\sigma}$。
* 使用高斯误差函数 (Error Function) 将 Z-Score 映射到概率空间$S_{tech} = \text{erf}(Z / \sqrt{2})$。


3. **自适应融合 (Adaptive Fusion)**:
* 权重基于信号的显著性：$W = \frac{|S|}{\sum|S|}$。
* 最终得分 = $S_{news} \cdot W_{news} + S_{tech} \cdot W_{tech}$。


4. **几何置信度 (Geometric Confidence)**:
* 计算新闻与技术面的线性距离，距离越小（信号越一致），置信度越高。



## 快速开始

### 1. 环境准备

确保已安装 Python 3.10+。

```bash
conda create -n fintech python=3.10
conda activate fintech
```

### 2. 安装依赖

需要安装 MCP SDK、LangChain 全家桶以及数据处理库。

```bash
pip install mcp langchain langchain-google-genai langgraph pandas numpy akshare pydantic
```

*(注意：请确保 `mcp` 库是最新版本，以支持 Stdio 连接)*

### 3. 配置 API Key

你需要一个 Google Gemini 的 API Key。

* **方式 A**: 设置环境变量
```bash
export GOOGLE_API_KEY="your_api_key_here"
```


* **方式 B**: 直接运行程序，程序会提示输入 Key。

### 4. 运行系统

直接运行客户端脚本：

```bash
python client.py
```

## 使用示例

### 场景一：基础查询 (Fast System)

> **User**: "茅台现在的价格是多少？"
> **AI**: 调用 `MarketData` -> 返回贵州茅台实时行情。

### 场景二：深度分析 (Slow System)

> **User**: "分析一下现在的市场情绪，特别是半导体行业。"
> **AI**:
> 1. **Thinking**: 调用 `ReasoningEngine` 规划步骤（先查新闻，再查指数，最后计算）。
> 2. **Action 1**: 并发调用 `MarketNews` 获取最新消息。
> 3. **Action 2**: 调用 `MarketData` 获取半导体板块实时涨跌。
> 4. **Action 3**: LLM 对新闻打分，结合行情调用 `MarketColor` 进行量化计算。
> 5. **Output**: 生成包含情绪分、置信度、驱动事件的结构化 Markdown 报告。

## 免责声明

本项目仅供学习研究使用。

1. **数据延迟**: 提供的行情数据来源于互联网公开接口 (AkShare)，可能存在延迟或不准确。
2. **非投资建议**: AI 生成的分析报告仅基于统计概率和文本模型，**不构成任何投资建议**。
3. **风险提示**: 金融市场有风险，投资需谨慎。

---

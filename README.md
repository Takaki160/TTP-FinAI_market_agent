
-----

# AI-Powered Market Intelligence (UBS Future Stars Program)

## 📌 项目概述 (Project Overview)

本项目旨在开发一个 **AI 驱动的分析层**，通过整合实时市场数据、行业动态和隔夜新闻，将非结构化的“市场叙事（Market Color）”转化为可操作的量化洞察。

### 核心挑战

  * **叙事转量化**：将模糊的文字描述转化为交易员、风险管理者和量化分析师可以直接使用的情绪得分、影响指标和置信水平。
  * **业务聚焦**：针对融资与借贷市场（Funding & Lending Markets）以及 Delta 1 产品进行深度优化。

-----

## 🏗 技术架构 (Architecture)

本项目采用高度模块化的智能体架构，核心组件包括：

  * **LLM Provider**: 使用 OpenAI/GPT 作为核心逻辑推理引擎。
  * **Orchestration**: 利用 **LangChain** 和 **LangGraph** 构建具有状态管理和反馈循环的复杂分析流。
  * **Data Access (MCP)**: 采用 **Model Context Protocol (MCP)** 架构，实现市场数据、新闻和持仓数据的标准化、即插即用式接入。
  * **UI/Chatbot**: 为交易员提供直观的交互界面和洞察展示。

-----

## 🛠 技术栈 (Tech Stack)

  * **语言**: Python
  * **AI 框架**: LangChain, LangGraph
  * **协议**: Model Context Protocol (MCP)
  * **模型**: 大语言模型 (LLMs)
  * **业务领域**: Delta 1 产品, 融资与借贷市场

-----

## 📅 项目规划 (Project Milestones)

| 里程碑 | 交付目标 | 关键内容 | 状态 |
| :--- | :--- | :--- | :--- |
| **\#1** | **基础架构与计划** | 建立市场数据服务器 (MCP Server)，确定组长与项目计划 | ⏳ 进行中 |
| **\#2** | **数据管道与解析** | 实时新闻采集模块，市场色彩（Market Color）解析引擎 | 📅 待开始 |
| **\#3** | **量化算法实现** | 情绪评分、影响指标、置信度水平算法开发 | 📅 待开始 |
| **\#4** | **集成与可视化** | 聚合洞察展示，完成最终系统 Demo | 📅 待开始 |

-----

## 🚀 Milestone \#1 快速开始 (Getting Started)

### 1\. 基础架构 (Basic Infra)

目前已初步实现能够回答股票、指数及指数期货价格的市场数据服务器。

```bash
# 安装依赖 (示例)
pip install mcp yfinance langchain

# 运行市场数据 MCP Server (开发中)
python servers/market_data_server.py
```

### 2\. 下周二目标清单

  * [ ] **团队分工**：确定 Team Lead 及其职责。
  * [ ] **项目计划**：细化各阶段交付时间线。
  * [ ] **功能验证**：确保服务器能正确返回特定资产（如股票/期货）的最新价格。

-----

## 👥 团队成员 (Team)

  * **Team Lead**: [你的名字/待定]
  * **Technical Lead**: [成员名字]
  * **Business/Product Analyst**: [成员名字]

-----

*UBS "Future Stars" Program - 2025*

-----
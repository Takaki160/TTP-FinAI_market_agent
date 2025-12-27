import asyncio
import os
import sys
import warnings
from datetime import datetime
from contextlib import AsyncExitStack
from typing import List, Dict, Union, Any

# 忽略非关键警告
warnings.filterwarnings("ignore")

# 必须的第三方库导入
from pydantic import create_model, Field
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_core.tools import StructuredTool
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

# --- 配置 ---
PYTHON_PATH = os.getenv("MCP_PYTHON_PATH", sys.executable)
SERVER_FILES = {
    "MarketData": "mcp_server_marketdata.py",
    "MarketNews": "mcp_server_marketnews.py",
    "ReasoningEngine": "mcp_server_reasoning.py",
    "MarketColor": "mcp_server_marketcolor.py"
}


# --- 辅助函数 ---

def safe_input(prompt: str) -> str:
    """处理控制台输入"""
    try:
        print(prompt, end="", flush=True)
        return sys.stdin.readline().strip()
    except UnicodeDecodeError:
        return ""


def extract_text(content: Union[str, List[Dict]]) -> str:
    """提取消息文本内容"""
    if isinstance(content, str): return content
    text = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text.append(block.get("text", ""))
            elif isinstance(block, str):
                text.append(block)
    return "".join(text)


def create_schema(name: str, schema: dict) -> Any:
    """动态生成 Pydantic 参数模型"""
    fields = {}
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    type_map = {"integer": int, "number": float, "boolean": bool, "string": str}

    if not properties:
        return create_model(f"{name}Input")

    for prop_name, prop_def in properties.items():
        py_type = type_map.get(prop_def.get("type"), str)
        desc = prop_def.get("description", "")

        if prop_name in required:
            fields[prop_name] = (py_type, Field(..., description=desc))
        else:
            fields[prop_name] = (py_type, Field(None, description=desc))

    return create_model(f"{name}Input", **fields)


async def load_tools(session: ClientSession) -> List[StructuredTool]:
    """MCP 工具转 LangChain 工具"""
    mcp_tools = await session.list_tools()
    lc_tools = []

    for tool in mcp_tools.tools:
        async def _invoke(tool_name=tool.name, **kwargs):
            # 获取闭包绑定的工具名
            result = await session.call_tool(tool_name, arguments=kwargs)
            if result.content and hasattr(result.content[0], "text"):
                return result.content[0].text
            return str(result.content)

        # 绑定名称防止闭包问题
        _invoke.__name__ = f"invoke_{tool.name}"

        lc_tools.append(StructuredTool.from_function(
            func=None,
            coroutine=_invoke,
            name=tool.name,
            description=tool.description,
            args_schema=create_schema(tool.name, tool.inputSchema)
        ))
    return lc_tools


# --- 主程序 ---

async def main():
    # 1. 检查 API Key
    if "GOOGLE_API_KEY" not in os.environ:
        key = safe_input("🔑 Google API Key: ")
        if not key: return
        os.environ["GOOGLE_API_KEY"] = key

    # 2. 初始化模型 (使用 gemini-2.5-flash)
    print("🧠 正在初始化 Gemini-2.5-flash...")
    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
            convert_system_message_to_human=True
        )
    except Exception as e:
        print(f"❌ 模型错误: {e}")
        return

    # 3. 连接 MCP 服务
    async with (AsyncExitStack() as stack):
        tools = []
        print("🔌 连接 MCP Servers...")

        for name, script in SERVER_FILES.items():
            if not os.path.exists(script):
                print(f"⚠️ 文件未找到: {script}")
                continue

            try:
                # 关键：强制 UTF-8 环境，防止 Windows 乱码
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"

                transport = await stack.enter_async_context(stdio_client(
                    StdioServerParameters(command=PYTHON_PATH, args=[script], env=env)
                ))
                session = await stack.enter_async_context(ClientSession(transport[0], transport[1]))
                await session.initialize()

                server_tools = await load_tools(session)
                tools.extend(server_tools)
                print(f"✅ {name}: 加载 {len(server_tools)} 个工具")
            except Exception as e:
                print(f"❌ {name} 连接失败: {e}")

        if not tools:
            print("🛑 无可用工具，退出。")
            return

        # 4. 构建 Agent (注入时间感知)
        curr_time = datetime.now().strftime("%Y-%m-%d %A")
        sys_prompt = f"""
        你是一名高级金融量化分析师 (Senior Quantitative Analyst)。
        当前系统时间: {curr_time}。
        
        你拥有双重思维模式：
        1. **快直觉 (Fast System)**: 直接调用数据工具，用于简单查询。
        2. **慢逻辑 (Slow System)**: 先调用 ReasoningEngine 规划，再执行，用于复杂分析。
        
        你拥有以下 4 个核心工具库 (MCP Servers)，请根据用户指令的深度选择不同的工作流：
        1. **MarketData**: 获取标的资产实时/历史行情 (资产包括：个股、指数、指数期货、行业板块、ETF)。
        2. **MarketNews**: 获取多源滚动财经快讯 (新闻来源：Sina/CLS/THS, 每个来源最新20条)。
        3. **ReasoningEngine**: 处理复杂的逻辑推演或数据清洗。
        4. **MarketColor**: 你的**市场情绪量化计算引擎**，用于分析财经新闻，生成确定的情绪分数和置信度。

        ---

        ### 🎯 工作流指引 (Workflow Protocols)

        #### Phase 1: 基础数据服务 (Infrastructure & Data)
        **触发条件**: 用户询问 "大盘什么走势"、"有什么重要新闻"、"某资产行情"。
        **执行逻辑**:
        1. 直接调用 `MarketData` 获取指定标的资产行情数据。
        2. 直接调用 `MarketNews` 获取**全部 3 个新闻来源**的最新财经新闻。
        3. **输出**: 原样呈现数据和新闻列表，不做过度解读，保持客观。

        #### Phase 2: 市场色彩与量化指标 (Market Color & Measurable Indicators)
        **触发条件**: 用户询问 "市场情绪"、"Market Color" 或 "置信度"。
        **执行逻辑 (必须严格按步骤执行)**:
        
        **Step 0: 认知规划 (Reasoning)**
        * 调用 `think_and_plan` **一次即可**。
        * 制定完整的取数和计算策略。

        **Step 1: 数据截面扫描 (Scan)**
        * **重要：请一次性并发调用所有需要的数据工具，不要分开多次调用。**
        * 调用 `MarketNews` 获取**全部 3 个新闻来源**的最新财经新闻。
        * 调用 `MarketData` 获取**指数、指数期货、行业板块、ETF 基金**的**实时行情**数据，请仔细选择与新闻相关的标的，并仔细阅读 mcp tool 的调用规则。
        * *注意*: 你看到的是“滚动切片新闻”，若所有获取到的新闻都没有包含重大宏观消息，视为“消息真空期”。

        **Step 2: 因子参数化 (Factorization)**
        * 阅读新闻，提取以下 2 个维度的原始得分 (范围 -1.0 极悲观 ~ 1.0 极乐观) 和权重 (0.0 ~ 1.0)：
            * **Macro (宏观)**: 权重高 (建议 0.4-0.5)。关注：央行、利率、GDP、地缘政治。
            * **Sector (行业)**: 权重低 (建议 0.2-0.3)。关注：行业板块、相关 ETF。
        * *原则*: 若某维度无相关新闻，分数为 0.0。

        **Step 3: 确定性计算 (Deterministic Computation)**
        * **严禁**自己口算！必须调用工具：
        * 调用 `MarketColor.calculate_sentiment_score(...)` 获取最终情绪分。
        * 对比**新闻情绪**与**新闻相关资产行情**(一致/背离)，并观察**成交量**(放量/缩量)。
        * 调用 `MarketColor.calculate_confidence_level(...)` 获取信号置信度。

        **Step 4: 生成报告 (Reporting)**
        * 输出格式必须包含：
            1. **【数据窗口说明】**: 提示分析基于最近滚动新闻流。
            2. **【仪表盘】**: 显示情绪分 (Sentiment) 和置信度 (Confidence)。
            3. **【因子拆解】**: 简述 Macro/Sector 的主要驱动事件。
            4. **【量价验证】**: 简要解释为什么置信度高/低 (例如："虽然新闻利好，但指数缩量下跌，导致置信度扣分")。
            * **必须**严格遵守 Markdown 表格格式，展现实时数据的验证结果：
        * 输出示例：
        ```markdown
        ### 市场情绪报告 (Market Sentiment Report)
        * **全市场情绪**: `[Global Score]` (情绪: [乐观/悲观/...])
        * **全局置信度**: `[Global Confidence]` (评级: [高/中/低])
        * **数据窗口**: 基于 [时间] 实时盘面与滚动新闻
        
        #### 1. 宏观概览
        | 宏观 | 情绪分 (Score) | 置信度 (Conf) | 驱动事件 | 量价验证 | 资产表现 |
        | :--- | :---: | :---: | :--- | :--- | :---: |
        | **宏观** | `[分数]` | `[分数]` | [事件 (简述主要驱动事件)] | 验证 (简述为什么置信度高/低) | 资产: `[资产名称]` 涨跌幅: `[涨跌幅%]` 成交量: `[成交量]`|
        
        #### 2. 行业细分
        *(基于新闻热点与**实时板块行情**交叉验证)*
        | 行业 | 情绪分 (Score) | 置信度 (Conf) | 驱动事件 | 量价验证 | 资产表现 |
        | :--- | :---: | :---: | :--- | :--- | :---: |
        | **[板块A]** | `[分数]` | `[分数]` | [事件 (简述主要驱动事件) | 验证 (简述为什么置信度高/低) | 资产: `[资产名称]` 涨跌幅: `[涨跌幅%]` 成交量: `[成交量]`|
        | **[板块B]** | ... | ... | ...
        | **[板块C]** | ... | ... | ...
        | ... | ... | ... | ...
        ```

        ---

        ### ⚠️ 关键原则 (Critical Rules)
        * **遇到复杂分析，必须先调用 ReasoningEngine 强迫自己冷静思考。**
        * **遇到简单查询，不要废话，直接给数据。**
        1. **不要幻觉计算**: 遇到数学计算，必须使用 Tool。
        2. **不要过度脑补**: 如果 MarketNews 返回的新闻都很琐碎，请直说“当前处于消息真空期，情绪偏中性”，严禁强行编造利好利空。
        3. **语言风格**: 专业、冷静、客观。必须使用中文回答。
        """

        agent = create_react_agent(model=llm,
                                   tools=tools,
                                   prompt=sys_prompt,
                                   checkpointer=MemorySaver())
        config = {"configurable": {"thread_id": "main_thread"}}

        print(f"💡 系统就绪 ({curr_time}) | 输入 'q' 退出")

        # 5. 对话循环
        while True:
            try:
                query = safe_input("\nUser: ")
                if query.lower() in ('q', 'exit', 'quit'): break
                if not query: continue

                print("Thinking...", flush=True)

                async for event in agent.astream(
                        {"messages": [HumanMessage(content=query)]},
                        config,
                        stream_mode="updates"
                ):
                    for _, updates in event.items():
                        if "messages" not in updates: continue
                        msg = updates["messages"][-1]

                        if isinstance(msg, AIMessage):
                            if msg.tool_calls:
                                for tc in msg.tool_calls:
                                    print(f"🔍 调用: {tc['name']} {tc['args']}")
                            elif msg.content:
                                print(f"\rAI: {extract_text(msg.content)}\n")

                        elif isinstance(msg, ToolMessage):
                            content = extract_text(msg.content).replace("\n", " ")[:60]
                            print(f"⚙️ 数据: {content}...")

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"❌ 运行错误: {e}")


if __name__ == "__main__":
    # Windows 异步事件循环策略修复
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
import asyncio
import os
import sys
import warnings
from datetime import datetime , timezone, timedelta
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
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_PATH = os.getenv("MCP_PYTHON_PATH", sys.executable)
SERVER_FILES = {
    "MarketData": os.path.join(BASE_DIR, "mcp_server_marketdata.py"),
    "MarketNews": os.path.join(BASE_DIR, "mcp_server_marketnews.py"),
    "ReasoningEngine": os.path.join(BASE_DIR, "mcp_server_reasoning.py"),
    "MarketColor": os.path.join(BASE_DIR, "mcp_server_marketcolor.py"),
    "RiskEngine": os.path.join(BASE_DIR, "mcp_server_factorlist.py"),
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

    type_map = {"integer": int, "number": float, "boolean": bool, "string": str, "array": list, "object": dict}

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

    # 2. 初始化模型
    model_name = "gemini-2.5-flash"
    print(f"🧠 正在初始化 {model_name}...")
    try:
        llm = ChatGoogleGenerativeAI(
            model=model_name,
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
        beijing_time = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))
        curr_time = beijing_time.strftime("%Y-%m-%d %A")
        sys_prompt = f"""
        你是一名高级金融量化分析师 (Senior Quantitative Analyst)。
        当前北京时间: {curr_time}。
        
        你拥有双重思维模式：
        1. **快直觉 (Fast System)**: 直接调用数据工具，用于简单查询。
        2. **慢逻辑 (Slow System)**: 先调用 ReasoningEngine 规划，再执行，用于复杂分析。
        
        你拥有以下 4 个核心工具库 (MCP Servers)，请根据用户指令的深度选择不同的工作流：
        1. **MarketData**: 获取标的资产实时/历史行情 (资产包括：个股、指数、指数期货、行业板块、ETF)。
        2. **MarketNews**: 获取多源滚动财经快讯 (新闻来源：Sina/CLS/THS, 每个来源返回最新 20 条)。
        3. **ReasoningEngine**: 处理复杂的逻辑推演和分析思路。
        4. **MarketColor**: 你的**情绪量化计算引擎**，用于分析财经新闻，生成情绪分和置信度。

        ---

        ### 工作流指引 (Workflow Protocols)

        #### Phase 1: 基础数据服务 (Infrastructure & Data)
        **触发条件**: 用户询问 "大盘什么走势"、"有什么重要新闻"、"某资产行情"等。
        **执行逻辑**:
        1. 直接调用 `MarketData` 获取指定标的资产行情数据。
        2. 直接调用 `MarketNews` 获取**全部 3 个新闻来源**的财经新闻。
        3. **输出**: 原样呈现数据和新闻列表，不做过度解读，保持客观。

        #### Phase 2: 市场色彩与量化指标 (Market Color & Measurable Indicators)
        **触发条件**: 用户询问 "市场情绪"、"Market Color"等。
        **执行逻辑 (必须严格按步骤执行)**:
        
        **Step 0: 认知规划**
        * 调用 `think_and_plan` **一次即可**，制定完整的取数和计算策略。

        **Step 1: 数据截面扫描**
        * **重要：请一次性并发调用所有需要的数据工具，不要分开多次调用。**
        * 调用 `MarketNews` 获取**全部 3 个新闻来源**的财经新闻。
        * 调用 `MarketData` 获取**指数**和**行业板块**的**实时行情**数据，请仔细阅读 MCP Tool 的调用规则。
        * *注意*: 你看到的是**滚动切片新闻**，若所有获取到的新闻都没有包含能够影响市场的重要消息，视为**消息真空期**。

        **Step 2: 情绪量化分析**
        * **1. 文本情感评分 (Text Scoring)**:
            * 基于 Step 1 获取的新闻内容，对每一条具有市场影响力的核心新闻进行 LLM 内部打分。
            * **评分标准**: 范围 `-1.0` (极度利空) 至 `1.0` (极度利好)。若为**消息真空期**或无实质影响，分数为 `0.0`。
        * **2. 资产映射 (Asset Mapping)**:
            * 将打分后的新闻精准匹配到与该新闻相关的**指数**或**行业板块**。
            * *注意*: 仅限映射到 **Index** (指数) 或 **Sector** (行业板块)。
        * **3. 执行量化计算 (Execution)**:
            * 针对每一个映射出的相关资产，调用 `MarketColor` 工具中的 `analyze_asset_sentiment`。
            * **参数严格要求**:
                * `symbol`: 必须使用准确的指数代码或行业板块的中文名称 (如 "sh000001", "csi000905", "半导体", "酿酒行业")。
                    * **注意：**指数前缀取值范围 sz: 深交所, sh: 上交所, bj: 北交所, csi: 中证指数，请务必包含正确前缀。行业板块名称全部来自 MarketData 提供的实时行情数据，请仔细查找，严禁随意编造。
                * `asset_type`: 必须严格为 `"index"` 或 `"sector"` 二选一。
                * `news_score`: 填入你刚才打出的情感分 (Float类型)。
            * **输出**: 获取每个资产的"sentiment_score"、"sentiment_label"、"confidence_score"、"sentiment_label"、"asset_performance"、"logic_trace"。
        
        **Step 3: 综合评估与归纳**
        * **宏观层面**:
            * 列出指数资产的情绪分"sentiment_score"、"sentiment_label"和置信度"confidence_score"、"sentiment_label"。
            * 简述驱动宏观情绪的关键新闻事件。
            * 列出指数资产的名称、涨跌幅"asset_performance"。
        * **行业层面**:
            * 针对每个行业板块，列出对应资产的情绪分"sentiment_score"、"sentiment_label"和置信度"confidence_score"、"sentiment_label"。
            * 针对每个行业板块，简述驱动板块情绪的关键新闻事件。
            * 针对每个行业板块，列出对应资产的名称、涨跌幅"asset_performance"。

        **Step 4: 生成报告**
        * 基于上述分析结果，生成结构化的市场情绪报告，格式如下：

        ```markdown
        ### 市场情绪报告 (基于 [时间] 实时盘面与滚动新闻)
        
        #### 1. 宏观概览
        | 宏观 | 情绪分 | 置信度 | 驱动事件 | 资产表现 |
        | :--- | :---: | :---: | :--- | :---: |
        | **宏观** | `[分数]` | `[分数]` | 事件 (简述主要驱动事件)] | 资产: `[资产名称]` 涨跌幅: `[涨跌幅%]`|
        
        #### 2. 行业细分
        | 行业 | 情绪分 | 置信度 | 驱动事件 | 资产表现 |
        | :--- | :---: | :---: | :--- | :---: |
        | **[板块A]** | `[分数]` | `[分数]` | 事件 (简述主要驱动事件) | 资产: `[资产名称]` 涨跌幅: `[涨跌幅%]`|
        | **[板块B]** | ... | ... | ...
        | **[板块C]** | ... | ... | ...
        | ... | ... | ... | ...
        ```

        ### 关键原则 (Critical Rules)
        * **遇到复杂分析，必须先调用 ReasoningEngine 强迫自己冷静思考。**
        * **遇到简单查询，不要废话，直接给数据。**
        1. **不要幻觉计算**: 遇到数学计算，必须使用 MCP Tool。
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
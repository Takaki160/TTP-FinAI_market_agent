import asyncio
import os
import sys
import logging
import warnings
from contextlib import AsyncExitStack
from typing import Any, Type, List, Dict, Union

# 屏蔽特定警告
warnings.filterwarnings("ignore", message=".*create_react_agent.*")
warnings.filterwarnings("ignore", category=UserWarning, module="langgraph")
warnings.filterwarnings("ignore", category=DeprecationWarning)

from pydantic import create_model, Field, BaseModel
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from langchain_core.tools import StructuredTool
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

# --- 全局配置 ---
# 请确保此处路径正确
PYTHON_PATH = os.getenv("MCP_PYTHON_PATH", sys.executable)

SERVER_SCRIPTS = {
    "MarketData": "mcp_server_marketdata.py",
    "MarketNews": "mcp_server_marketnews.py"
}

# 基础日志配置 (只显示错误)
logging.basicConfig(level=logging.ERROR)
logging.getLogger("mcp").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.ERROR)


# --- 辅助功能 ---

def safe_input(prompt: str) -> str:
    """兼容各类控制台的输入函数"""
    print(prompt, end="", flush=True)
    return sys.stdin.readline().strip()


def extract_text_content(content: Union[str, List[Dict]]) -> str:
    """清洗 AI 返回的内容，处理复杂列表结构"""
    if isinstance(content, str):
        return content

    text_parts = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif isinstance(block, str):
                text_parts.append(block)

    return "".join(text_parts) if text_parts else str(content)


def create_tool_schema(tool_name: str, input_schema: dict) -> Type[BaseModel]:
    """将 MCP JSON Schema 转换为 Pydantic 模型"""
    fields = {}
    properties = input_schema.get("properties", {})
    required_fields = input_schema.get("required", [])

    type_map = {
        "integer": int,
        "number": float,
        "boolean": bool
    }

    for name, prop in properties.items():
        py_type = type_map.get(prop.get("type"), str)
        desc = prop.get("description", "")

        field_info = Field(..., description=desc) if name in required_fields else Field(None, description=desc)
        fields[name] = (py_type, field_info)

    return create_model(f"{tool_name}Input", **fields)


# --- 核心逻辑 ---

async def load_mcp_tools(session: ClientSession) -> List[StructuredTool]:
    """从 MCP Session 加载并转换工具"""
    mcp_tools_list = await session.list_tools()
    langchain_tools = []

    for tool in mcp_tools_list.tools:
        async def _invoke(tool_name=tool.name, **kwargs):
            result = await session.call_tool(tool_name, arguments=kwargs)
            # 尝试提取文本内容
            if result.content and hasattr(result.content[0], "text"):
                return result.content[0].text
            return str(result.content)

        lc_tool = StructuredTool.from_function(
            func=None,
            coroutine=_invoke,
            name=tool.name,
            description=tool.description,
            args_schema=create_tool_schema(tool.name, tool.inputSchema)
        )
        langchain_tools.append(lc_tool)

    return langchain_tools


async def main():
    # 0. 环境检查
    if not os.path.exists(PYTHON_PATH):
        print(f"❌ 错误: Python 解释器路径不存在: {PYTHON_PATH}")
        return

    # 1. API Key 配置
    if "GOOGLE_API_KEY" not in os.environ:
        api_key = safe_input("请输入 Google API Key: ")
        if not api_key:
            return
        os.environ["GOOGLE_API_KEY"] = api_key

    print("🧠 初始化 Agent...")
    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
            convert_system_message_to_human=True
        )
    except Exception as e:
        print(f"❌ 模型初始化失败: {e}")
        return

    # 2. 连接 MCP Servers
    async with AsyncExitStack() as stack:
        all_tools = []

        print("🔌 连接工具服务...")
        for name, script in SERVER_SCRIPTS.items():
            full_path = os.path.abspath(script)
            if not os.path.exists(full_path):
                print(f"⚠️ 跳过: 文件未找到 {script}")
                continue

            try:
                # 启动子进程并建立连接
                transport = await stack.enter_async_context(
                    stdio_client(StdioServerParameters(
                        command=PYTHON_PATH,
                        args=[full_path],
                        env=os.environ.copy()
                    ))
                )
                session = await stack.enter_async_context(ClientSession(transport[0], transport[1]))
                await session.initialize()

                tools = await load_mcp_tools(session)
                print(f"✅ {name}: 已加载 {len(tools)} 个工具")
                all_tools.extend(tools)
            except Exception as e:
                print(f"❌ {name} 连接失败: {e}")

        if not all_tools:
            print("🛑 无可用工具，程序退出")
            return

        # 3. 创建 Graph Agent
        graph = create_react_agent(
            model=llm,
            tools=all_tools,
            checkpointer=MemorySaver()
        )

        print("-" * 50)
        print("💡 助手就绪 (输入 'q' 退出)")

        config = {"configurable": {"thread_id": "session-01"}}

        # 4. 对话循环
        while True:
            try:
                user_msg = safe_input("\nUser: ")
                if user_msg.lower() in ["q", "quit", "exit"]:
                    break
                if not user_msg:
                    continue

                print("Thinking...", flush=True)

                async for event in graph.astream(
                        input={"messages": [HumanMessage(content=user_msg)]},
                        config=config,
                        stream_mode="updates"
                ):
                    for _, updates in event.items():
                        if "messages" not in updates: continue

                        last_msg = updates["messages"][-1]

                        # 处理工具调用显示
                        if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
                            for tc in last_msg.tool_calls:
                                print(f"🔍 [调用工具] {tc['name']}")

                        # 处理 AI 回复 (关键修复：清洗文本)
                        elif isinstance(last_msg, AIMessage) and last_msg.content:
                            clean_content = extract_text_content(last_msg.content)
                            if clean_content.strip():
                                print(f"\rAI: {clean_content}\n")

                        # 处理工具返回显示
                        elif isinstance(last_msg, ToolMessage):
                            # 仅显示前100个字符避免刷屏
                            preview = extract_text_content(last_msg.content).replace("\n", " ")[:100]
                            print(f"⚙️ [数据返回] {preview}...")

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"\n❌ 发生错误: {e}")


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
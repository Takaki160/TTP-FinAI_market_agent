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
    "MarketNews": "mcp_server_marketnews.py"
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
        async def _invoke(**kwargs):
            # 获取闭包绑定的工具名
            t_name = tool.name
            result = await session.call_tool(t_name, arguments=kwargs)
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
    async with AsyncExitStack() as stack:
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
        sys_prompt = f"你是一个金融助手。当前时间: {curr_time}。根据此时间处理'最近'或'过去x天'的日期计算。使用中文回答。"

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
import sys
import io
from mcp.server.fastmcp import FastMCP

# --- 环境适配：强制标准输出为 UTF-8 ---
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- LLM 系统指令 ---
INSTRUCTIONS = """
这是一个专门用于系统性思考和规划的工具。
它不获取新信息，而是跟踪思考过程。
在调用任何其他数据获取工具之前，必须先使用这个工具来组织你的策略。
"""

mcp = FastMCP(name="ReasoningEngine", instructions=INSTRUCTIONS)

# --- 工具定义 ---
@mcp.tool()
def think_and_plan(thought: str, plan: str, action: str, thoughtNumber: str) -> dict:
    """
    This is a tool designed for systematic thinking and planning.
    It does not acquire new information but tracks the thinking process.
    Use this BEFORE calling any other data fetching tools to organize your strategy.

    Parameters:
    - thought: Current analysis or hypothesis.
    - plan: Step-by-step plan for the immediate future.
    - action: The specific tool you intend to call next.
    - thoughtNumber: A sequential identifier (e.g., "Step 1", "Step 2").
    """
    print(f"🤔 [THOUGHT]: {thought}")
    print(f"📋 [PLAN]: {plan}")
    print(f"👉 [ACTION]: {action}")

    return {
        "thought": thought,
        "plan": plan,
        "action": action,
        "thoughtNumber": thoughtNumber,
        "status": "stored_in_memory"
    }


if __name__ == "__main__":
    mcp.run()
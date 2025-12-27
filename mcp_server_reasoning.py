import sys
import io
from mcp.server.fastmcp import FastMCP

# 强制 UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

mcp = FastMCP(name="ReasoningEngine")


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
    # 这里的 print 是为了在服务器端控制台能看到它的思考过程（可选）
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
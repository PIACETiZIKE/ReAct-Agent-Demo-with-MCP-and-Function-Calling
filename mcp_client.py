import asyncio
from typing import Optional, List, Dict, Any
from contextlib import AsyncExitStack
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class MCPClient:
    def __init__(self, server_script_path: str):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.server_script_path = server_script_path
        self.tools: List[Any] = []

    async def connect_to_server(self):
        """Connect to the MCP server"""
        # 确定使用 Python 运行服务器脚本
        is_python = self.server_script_path.endswith('.py')
        if not is_python:
            raise ValueError("Server script must be a .py file")

        command = "python"
        server_params = StdioServerParameters(
            command=command,
            args=[self.server_script_path],
            env=None
        )

        # 创建 stdio 传输并初始化会话
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        stdio, write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(stdio, write))

        # 初始化会话
        await self.session.initialize()

        # 获取可用工具列表
        response = await self.session.list_tools()
        self.tools = response.tools
        print(f"\n已连接到服务器，发现 {len(self.tools)} 个工具: {[tool.name for tool in self.tools]}")

    async def call_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """调用MCP工具"""
        if not self.session:
            raise RuntimeError("未连接到服务器")

        call_tool_result = await self.session.call_tool(tool_name, tool_args)
        return call_tool_result.content[0].text

    async def __aenter__(self):
        """初始化资源"""
        await self.connect_to_server()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """清理资源"""
        await self.exit_stack.aclose()


async def main():
    """测试 MCP 客户端"""
    # 获取 MCP 服务器路径
    mcp_server_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "mcp_server.py"))

    if not os.path.exists(mcp_server_path):
        print(f"错误: 找不到服务器脚本 {mcp_server_path}")
        return

    async with MCPClient(mcp_server_path) as client:
        # 测试工具调用
        tools = await client.session.list_tools()
        print(f"可用工具: {[tool.name for tool in tools]}")

        # 测试列出当前目录
        try:
            result = await client.call_tool("list_directory", {"directory_path": "."})
            print(f"目录列表: {result}")
        except Exception as e:
            print(f"工具调用失败: {e}")


if __name__ == "__main__":
    asyncio.run(main())
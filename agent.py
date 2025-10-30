
import os
import re
import json
from string import Template
import asyncio

import click
from dotenv import load_dotenv
from openai import OpenAI
import platform

from prompt_template import react_system_prompt_template
from mcp_client import MCPClient


class ReActAgent:
    def __init__(self, mcp_client:MCPClient, model: str, project_directory: str):
        self.mcp_client = mcp_client
        self.model = model
        self.project_directory = project_directory
        self.client = OpenAI(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=ReActAgent.get_api_key(),
        )
        self.tools = []

    async def initialize(self):
        """初始化工具信息"""
        self.tools = [{
            "type": "function",  # 添加类型标识
            "function": {  # 函数信息包裹在function字段中
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema  # 原input_schema对应parameters字段
            }
        } for tool in self.mcp_client.tools]

    async def run(self, user_input: str):
        messages = [
            # 系统提示词
            {"role": "system", "content": self.render_system_prompt(react_system_prompt_template)},
            # 用户提出的问题
            {"role": "user", "content": f"<question>{user_input}</question>"}
        ]

        while True:

            # 请求模型
            content = self.call_model(messages)

            # 检测 Thought，从content字符串中查找并提取被<thought>和</thought>标签包裹的内容
            # re.DOTALL：标志位，使.可以匹配包括换行符在内的所有字符
            thought_match = re.search(r"<thought>(.*?)</thought>", content, re.DOTALL)
            if thought_match:
                thought = thought_match.group(1)
                print(f"\n\n💭 Thought: {thought}")

            # 检测模型是否输出 Final Answer，如果是的话，直接返回
            if "<final_answer>" in content:
                final_answer = re.search(r"<final_answer>(.*?)</final_answer>", content, re.DOTALL)
                return final_answer.group(1)

            # 检测 Action
            action_match = re.search(r"<action>(.*?)</action>", content, re.DOTALL)
            if not action_match:
                raise RuntimeError("模型未输出 <action>")

            try:
                # 解析JSON格式的action
                action_data = json.loads(action_match.group(1).strip())
                tool_name = action_data["name"]
                tool_args = action_data["parameters"]
            except (json.JSONDecodeError, KeyError) as e:
                raise RuntimeError(f"工具调用格式错误: {str(e)}")

            print(f"\n\n🔧 Action: {tool_name}({tool_args})")

            # 只有终端命令才需要询问用户，其他的工具直接执行
            should_continue = input(f"\n\n是否继续？（Y/N）") if tool_name == "run_terminal_command" else "y"
            if should_continue.lower() != 'y':
                print("\n\n操作已取消。")
                return "操作被用户取消"

            try:
                # 调用MCP工具
                observation = await self.mcp_client.call_tool(tool_name, tool_args)
            except Exception as e:
                observation = f"工具执行错误：{str(e)}"

            print(f"\n\n🔍 Observation：{observation}")
            obs_msg = f"<observation>{observation}</observation>"
            # 把工具执行结果observation添加到message里
            messages.append({"role": "user", "content": obs_msg})

    def render_system_prompt(self, system_prompt_template: str) -> str:
        """渲染系统提示模板，替换变量"""
        tool_list = self.tools if self.tools else "无"
        current_directory = self.project_directory
        return Template(system_prompt_template).substitute(
            operating_system = self.get_operating_system_name(),
            tool_list = tool_list,
            current_directory = current_directory
        )

    @staticmethod
    def get_api_key() -> str:
        """Load the API key from an environment variable."""
        load_dotenv()
        api_key = os.getenv("API_KEY")
        if not api_key:
            raise ValueError("未找到 API_KEY 环境变量，请在 .env 文件中设置。")
        return api_key

    def call_model(self, messages):
        print("\n\n正在请求模型，请稍等...")
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools = self.tools,
        )
        content = response.choices[0].message.content
        messages.append({"role": "assistant", "content": content})
        return content

    def get_operating_system_name(self):
        os_map = {
            "Darwin": "macOS",
            "Windows": "Windows",
            "Linux": "Linux"
        }

        return os_map.get(platform.system(), "Unknown")


async def main():
    """主函数"""
    project_dir = os.path.abspath(os.path.dirname(__file__))

    # 获取 MCP 服务器路径
    mcp_server_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "mcp_server.py"))

    if not os.path.exists(mcp_server_path):
        print(f"错误: 找不到 MCP 服务器脚本 {mcp_server_path}")
        return

    try:
        # 创建 MCP 客户端并连接
        async with MCPClient(mcp_server_path) as mcp_client:
            # 创建 Agent 并初始化
            agent = ReActAgent(mcp_client=mcp_client, model="qwen3-coder-plus", project_directory=project_dir)
            await agent.initialize()

            task = input("请输入任务：")
            final_answer = await agent.run(task)
            print(f"\n\n✅ Final Answer：{final_answer}")

    except Exception as e:
        print(f"运行失败: {e}")

if __name__ == "__main__":
    asyncio.run(main())

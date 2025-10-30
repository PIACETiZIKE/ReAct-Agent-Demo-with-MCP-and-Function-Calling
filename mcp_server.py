from typing import Any
import httpx
import os
import subprocess
from mcp.server.fastmcp import FastMCP

# 初始化FastMCP服务器
mcp = FastMCP("weather", log_level="ERROR")

# 常量
NWS_API_BASE = "https://api.weather.gov"
USER_AGENT = "weather-app/1.0"


async def make_nws_request(url: str) -> dict[str, Any] | None:
    """使用适当的错误处理向NWS API发出请求。"""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/geo+json"
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

def format_alert(feature: dict) -> str:
    """将警报特征格式化为可读字符串。"""
    props = feature["properties"]
    return f"""
事件: {props.get('event', '未知')}
区域: {props.get('areaDesc', '未知')}
严重性: {props.get('severity', '未知')}
描述: {props.get('description', '无可用描述')}
说明: {props.get('instruction', '无具体说明')}
"""

@mcp.tool()
async def get_alerts(state: str) -> str:
    """获取美国州的天气警报。

    参数:
        state: 两个字母的美国州代码（例如CA, NY）
    """
    url = f"{NWS_API_BASE}/alerts/active/area/{state}"
    data = await make_nws_request(url)

    if not data or "features" not in data:
        return "无法获取警报或未找到警报。"

    if not data["features"]:
        return "该州没有活跃的警报。"

    alerts = [format_alert(feature) for feature in data["features"]]
    return "\n---\n".join(alerts)

@mcp.tool()
async def get_forecast(latitude: float, longitude: float) -> str:
    """获取某地的天气预报。

    参数:
        latitude: 地点的纬度
        longitude: 地点的经度
    """
    # 首先获取预报网格端点
    points_url = f"{NWS_API_BASE}/points/{latitude},{longitude}"
    points_data = await make_nws_request(points_url)

    if not points_data:
        return "无法获取该位置的预报数据。"

    # 从点响应中获取预报URL
    forecast_url = points_data["properties"]["forecast"]
    forecast_data = await make_nws_request(forecast_url)

    if not forecast_data:
        return "无法获取详细预报。"

    # 将周期格式化为可读的预报
    periods = forecast_data["properties"]["periods"]
    forecasts = []
    for period in periods[:5]:  # 仅显示接下来的5个周期
        forecast = f"""
{period['name']}:
温度: {period['temperature']}°{period['temperatureUnit']}
风: {period['windSpeed']} {period['windDirection']}
预报: {period['detailedForecast']}
"""
        forecasts.append(forecast)

    return "\n---\n".join(forecasts)

@mcp.tool()
async def read_file(file_path: str) -> str:
    """读取文件内容。

    参数:
        file_path: 要读取的文件的绝对路径
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"读取文件错误：{str(e)}"

@mcp.tool()
async def write_to_file(file_path: str, content: str) -> str:
    """将内容写入文件。

    参数:
        file_path: 要写入的文件的绝对路径
        content: 要写入的内容
    """
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content.replace("\\n", "\n"))
        return "写入成功"
    except Exception as e:
        return f"写入文件错误：{str(e)}"

@mcp.tool()
async def run_terminal_command(command: str) -> str:
    """执行终端命令。

    参数:
        command: 要执行的终端命令
    """
    try:
        run_result = subprocess.run(command, shell=True, capture_output=True, text=True)
        return run_result.stdout if run_result.returncode == 0 else f"执行失败: {run_result.stderr}"
    except Exception as e:
        return f"执行终端命令错误：{str(e)}"

@mcp.tool()
async def list_directory(directory_path: str) -> str:
    """列出目录内容。

    参数:
        directory_path: 要列出内容的目录路径
    """
    try:
        items = os.listdir(directory_path)
        return "\n".join(items)
    except Exception as e:
        return f"列出目录错误：{str(e)}"


if __name__ == "__main__":
    # 初始化并运行服务器
    mcp.run(transport='stdio')
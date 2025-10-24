from mcp.server.fastmcp import FastMCP
from tools.weather import weather_tool
from tools.time import time_tool
from tools.calculator import calculator_tool
from tools.google_search import google_search_tool

mcp = FastMCP("Server")

weather_tool(mcp)
time_tool(mcp)
calculator_tool(mcp)
google_search_tool(mcp)

if __name__ == "__main__":
    mcp.run(transport='stdio')

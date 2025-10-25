import asyncio
import json
import re
import sys
from contextlib import AsyncExitStack
from typing import Optional
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from google import genai
from google.genai import types

load_dotenv()

# Convert TextContent objects into plain text
def extract_text(content_list):
    if isinstance(content_list, list):
        return "\n".join([
            c.text if hasattr(c, "text") else str(c)
            for c in content_list
        ])
    return str(content_list)

class MCPClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.genai_client = genai.Client()
        self.tools = []
        self.memory = []

    async def connect_to_server(self, server_script_path: str):
        """Connect to an MCP server)."""
        is_python = server_script_path.endswith(".py")
        if not (is_python):
            raise ValueError("Server script must be a .py")

        command = "python"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path]
        )

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()

        response = await self.session.list_tools()
        
        function_declarations = []
        for tool in response.tools:
            func = {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema,
            }
            function_declarations.append(func)
        print("\n✅ Connected to MCP server with tools:", [t["name"] for t in function_declarations])
        self.tools = [types.Tool(function_declarations=function_declarations)]

    async def process_query(self, query: str) -> str:
        """Send query to Gemini, detect tool use, execute it, and return final output."""
        if self.memory:
            memories = "\n".join(self.memory)
            context = self.genai_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=(
                    f"Summarize relevant things in '{memories}' based on current query '{query}' to be used as a context"
                ),
            )
            context = context.text.strip()
            query = f"User query: {query}\nRelevant context: {context}"

        # Step 1. Ask Gemini for a response
        llm_response = self.genai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=query,
            config=types.GenerateContentConfig(
                system_instruction=
                    "You are fAfAfIfI, a workout assistant bot, only answer workout related question and combine your answer with available tools, You can use external tools from the MCP server to improve your answers, You can use multiple external tools from the MCP server in one answer. Write each tool call on a new line, exactly in this format: @tool:tool_name(arg1=value1,arg2=value2). You may call multiple tools if the query needs multiple data sources.",
                thinking_config=types.ThinkingConfig(thinking_budget=10),
                safety_settings = [
                    types.SafetySetting(
                        category=category,
                        threshold=types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE
                    )
                    for category in [
                        types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                        types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                        types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                        types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT
                    ]
                ],
                tools = self.tools
            ),
        )

        candidate = llm_response.candidates[0]
        content_parts = candidate.content.parts if candidate.content.parts else None

        tool_results = []

        for part in content_parts:
            if hasattr(part, "function_call") and part.function_call:
                fn = part.function_call
                tool_name = fn.name
                json_args = fn.args or {}
                print(f"\n🧠 Gemini: wants to call tool '{tool_name}' with args {json_args}")

                print(f"🔧 Calling MCP tool '{tool_name}' with args {json_args} ...")
                try:
                    tool_result = await self.session.call_tool(tool_name, json_args)
                    tool_results.append({
                        "tool": tool_name,
                        "args": json_args,
                        "result": extract_text(tool_result.content)
                    })
                    print(f"📊 Tool result: {tool_result.content}")
                except Exception as e:
                    print(f"❌ Error calling '{tool_name}': {e}")

        if tool_results:
            combined_summary = json.dumps(tool_results, ensure_ascii=False)
            follow_up = self.genai_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=(
                    f"User query: {query}\n\n"
                    f"Tool results: {combined_summary}\n\n"
                    "Summarize the combined results into a coherent workout-related answer."
                ),
            )
            final_text = follow_up.text.strip()
            print(f"\n🤖 fAfAfIfI: {final_text}")
            self.memory.append(final_text)
            if len(self.memory) > 5:
                self.memory.pop(0)
            return final_text

        # ✅ Fallback: normal text response
        if llm_response.text:
            text = llm_response.text.strip()
            print(f"\n🧠 Gemini: {text}")
            self.memory.append(text)
            if len(self.memory) > 5:
                self.memory.pop(0)
            return text

        print("⚠️ No text or function call found in Gemini response.")
        return ""

    async def chat_loop(self):
        """Interactive chat loop."""
        print("\n💬 fAfAfIfI is ready! Type your workout question (or 'quit' to exit).")

        while True:
            query = input("\nYou: ").strip()
            if query.lower() == "quit":
                break
            try:
                await self.process_query(query)
            except Exception as e:
                print(f"❌ Error: {e}")

    async def cleanup(self):
        await self.exit_stack.aclose()


async def main():
    if len(sys.argv) < 2:
        print("Usage: python client.py <path_to_server_script>")
        sys.exit(1)

    client = MCPClient()
    try:
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())

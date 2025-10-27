import asyncio
import json
import sys
import psycopg
import os
from contextlib import AsyncExitStack
from typing import Optional
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from google import genai
from google.genai import types

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT")


# Convert TextContent objects into plain text
def extract_text(content_list):
    if isinstance(content_list, list):
        return "\n".join([
            c.text if hasattr(c, "text") else str(c)
            for c in content_list
        ])
    return str(content_list)


class MCPClient:
    def __init__(self, dbname, user, password, host, port):
        self.conn = psycopg.connect(
            dbname=dbname,
            user=user,
            password=password,
            host=host,
            port=port
        )
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.genai_client = genai.Client()
        self.tools = []
        self.memory = []

    # ✅ Fix SQL syntax
    def create_table(self):
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE EXTENSION IF NOT EXISTS vector;
                CREATE TABLE IF NOT EXISTS memory_vectors (
                    id SERIAL PRIMARY KEY,
                    server_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    embedding VECTOR(768) NOT NULL,
                    summary TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT NOW()
                );
            """)
            self.conn.commit()

    def insert_ltm(self, server_id, channel_id, thread_id, embedding, summary):
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO memory_vectors (server_id, channel_id, thread_id, embedding, summary)
                VALUES (%s, %s, %s, %s::vector, %s);
            """, (server_id, channel_id, thread_id, embedding, summary))
            self.conn.commit()

    def fetch_ltm(self, server_id, channel_id, thread_id, embedding):
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT summary
                FROM memory_vectors
                WHERE server_id = %s AND channel_id = %s AND thread_id = %s
                ORDER BY embedding <=> %s::vector
                LIMIT 3;
            """, (server_id, channel_id, thread_id, embedding))
            rows = cur.fetchall()
        return [r[0] for r in rows]

    def insert_stm(self, text: str):
        self.memory.append(text)
        if len(self.memory) > 5:
            self.memory.pop(0)

    # ✅ Typo: std → str
    def embed_result(self, text: str):
        result = self.genai_client.models.embed_content(
            model="models/text-embedding-004",
            contents=text
        )
        return result.embeddings[0].values

    async def connect_to_server(self, server_script_path: str):
        """Connect to an MCP server."""
        if not server_script_path.endswith(".py"):
            raise ValueError("Server script must be a .py file")

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
        """Send query to Gemini, detect tool use, and store relevant memories."""
        # === Retrieve similar LTM ===
        try:
            query_embedding = self.embed_result(query)
            ltm = self.fetch_ltm("cli", "cli", "cli", query_embedding)
        except Exception as e:
            print(f"⚠️ Fetch Long Term Memory failed: {e}")
            ltm = []
        relevant_memories = "\n".join(ltm)

        if self.memory:
            memories = "\n".join(self.memory)
            context = self.genai_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"Summarize '{memories}' into something like 'Running in Yogyakarta' or 'Workout for beginner' that is relevant to query {query}, always add city, name, place, time, situation, or activity name if it's included in memories, only include the summary and don't add anything else",
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_budget=10)
                ),
            ).text.strip()
            query = f"User query: {query}\nContext: {context}\nRelevant memories: {relevant_memories}"
            query = self.genai_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"Combine {query} into one complete query",
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_budget=10)
                ),
            ).text.strip()
            print(f"Refined Query: {query}")

        # === Call Gemini ===
        llm_response = self.genai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=query,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are fAfAfIfI, a workout assistant bot, only answer workout related question and combine your answer with available tools, You can use external tools from the MCP server to improve your answers, You can use multiple external tools from the MCP server in one answer. Write each tool call on a new line, exactly in this format: @tool:tool_name(arg1=value1,arg2=value2). You may call multiple tools if the query needs multiple data sources.",
                ),
                thinking_config=types.ThinkingConfig(thinking_budget=10),
                safety_settings=[
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
                tools=self.tools
            ),
        )

        candidate = llm_response.candidates[0]
        content_parts = candidate.content.parts if candidate.content.parts else None
        tool_results = []

        # === Execute any tool calls ===
        for part in content_parts or []:
            if hasattr(part, "function_call") and part.function_call:
                fn = part.function_call
                tool_name = fn.name
                json_args = fn.args or {}
                print(f"\n🧠 Gemini wants to call '{tool_name}' with args {json_args}")
                try:
                    tool_result = await self.session.call_tool(tool_name, json_args)
                    tool_results.append({
                        "tool": tool_name,
                        "args": json_args,
                        "result": extract_text(tool_result.content)
                    })
                except Exception as e:
                    print(f"❌ Error calling tool '{tool_name}': {e}")

        # === Summarize tool results ===
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
            return follow_up.text.strip()

        # === Fallback text ===
        if llm_response.text:
            return llm_response.text.strip()

        print("⚠️ No valid response from Gemini.")
        return ""

    async def chat_loop(self):
        """Interactive chat loop."""
        print("\n💬 fAfAfIfI is ready! Type your workout question (or 'quit' to exit).")
        while True:
            query = input("\nYou: ").strip()
            if query.lower() == "quit":
                break
            with open("logs/logs.txt", "a") as file:
                file.write("\nYou: " + query)
            try:
                final_text = await self.process_query(query)
                summary = self.genai_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=(
                        f"""
                        Summarize '{final_text}' into one concise sentence describing what happened in the conversation.  
                        Examples:  
                        - "User asked if it’s okay to run in the rain."  
                        - "Agent recommended a gym around Yogyakarta."  
                        Always include these details if present:
                        - City (e.g., "Yogyakarta", "Jakarta")  
                        - Weather (e.g., "rain", "sunny")  
                        - Time (e.g., "5 PM")  
                        - Day (e.g., "Monday")  
                        Only return the summary sentence — no explanations, quotes, or extra words.
                        """
                    ),
                ).text.strip()
                embedding = self.embed_result(summary)
                self.insert_stm(summary)
                self.insert_ltm("cli", "cli", "cli", embedding, summary)
                output = f"\nfAfAfIfI: {final_text}"
                print(output)
                with open("logs/logs.txt", "a") as file:
                    file.write(output)
            except Exception as e:
                print(f"❌ Error: {e}")

    async def cleanup(self):
        await self.exit_stack.aclose()


async def main():
    if len(sys.argv) < 2:
        print("Usage: python client.py <path_to_server_script>")
        sys.exit(1)

    client = MCPClient(DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT)
    client.create_table()
    try:
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())


import os
import discord
import asyncio
from dotenv import load_dotenv
from client import MCPClient

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT")
SERVER_PATH = os.getenv("SERVER_PATH")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# --- Setup Discord intents ---
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = discord.Client(intents=intents)

# --- Global MCP client ---
mcp_client: MCPClient | None = None


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

    global mcp_client
    # Initialize MCP client
    mcp_client = MCPClient(DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT)
    mcp_client.create_table()

    # Connect to MCP server
    await mcp_client.connect_to_server(SERVER_PATH)
    print("🧠 MCP client connected and ready.")


@bot.event
async def on_message(message):
    """Handle user messages from Discord."""
    if message.author == bot.user:
        return

    # Wait until MCP client is ready
    if not mcp_client:
        await message.channel.send("⚙️ MCP client not ready yet, please wait...")
        return

    # Only process messages starting with !fit
    if not message.content.startswith("!fit"):
        return

    user_input = message.content[len("!fit "):].strip()
    channel_id = str(message.channel.id)

    await message.channel.typing()

    try:
        # === Ask MCPClient to process the query ===
        final_text = await mcp_client.process_query(user_input, channel_id)

        mcp_client.process_output(final_text, channel_id)

        # === Send reply back to Discord ===
        await message.reply(f"🧠 {final_text[:1900]}")  # 2000 char Discord limit

    except Exception as e:
        print(f"❌ Error: {e}")
        await message.reply("⚠️ Sorry, something went wrong while processing your request.")


# --- Run bot ---
bot.run(DISCORD_TOKEN)

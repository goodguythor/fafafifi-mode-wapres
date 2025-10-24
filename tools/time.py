from datetime import datetime
from zoneinfo import ZoneInfo

def time_tool(mcp):
    @mcp.tool()
    def get_current_time(location: str = "Asia/Jakarta") -> dict:
        """Get the current local time for a given timezone (default: Asia/Jakarta)."""
        try:
            tz = ZoneInfo(location)
            now = datetime.now(tz)
            return {
                "timezone": location,
                "datetime": now.strftime("%d-%m-%Y %H:%M:%S"),
                "hour": now.hour
            }
        except Exception as e:
            return {"error": str(e)}

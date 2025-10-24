import os
import requests
from dotenv import load_dotenv

load_dotenv()

SERP_API_KEY = os.getenv("SERP_API_KEY")

def google_search_tool(mcp):
    @mcp.tool()
    def google_search(query: str, num_results: int = 5) -> dict:
        """Search Google for a query and return top results (title, link, snippet)."""
        if not SERP_API_KEY:
            return {"error": "Missing SERP_API_KEY environment variable"}

        if not query:
            return {"error": "Missing 'query' parameter."}

        url = "https://serpapi.com/search.json"
        params = {
            "q": query,
            "num": num_results,
            "api_key": SERP_API_KEY,
            "engine": "google",
            "hl": "en"
        }

        try:
            res = requests.get(url, params=params)
            res.raise_for_status()
            data = res.json()
        except Exception as e:
            return {"error": f"Failed to fetch search results: {e}"}

        if "error" in data:
            return {"error": data["error"]}

        results = []
        for item in data.get("organic_results", [])[:num_results]:
            results.append({
                "title": item.get("title"),
                "link": item.get("link"),
                "snippet": item.get("snippet")
            })

        return {"query": query, "results": results}

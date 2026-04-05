# __skill_name__ = "web_search"
# __skill_description__ = "Search the web using SearXNG and return results"
# __skill_active__ = True

import httpx
import os
import json
from urllib.parse import quote_plus


SEARXNG_URI = os.getenv("SEARXNG_URI", "http://server.hostname.com:8383")


async def execute(query: str, num_results: int = 5) -> str:
    """
    Search the web using a SearXNG instance and return results.

    Args:
        query: The search query string
        num_results: Maximum number of results to return (default: 5)

    Returns:
        Formatted search results as a string
    """
    try:
        search_url = f"{SEARXNG_URI}/search"
        params = {
            "q": query,
            "format": "json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(search_url, params=params)
            response.raise_for_status()
            data = response.json()

            results = data.get("results", [])

            if not results:
                return f"No results found for: {query}"

            # Format the top results
            formatted = []
            for i, result in enumerate(results[:num_results], 1):
                title = result.get("title", "No title")
                url = result.get("url", "")
                content = result.get("content", "No description")

                # Truncate long content
                if len(content) > 300:
                    content = content[:297] + "..."

                formatted.append(
                    f"{i}. {title}\n"
                    f"   {url}\n"
                    f"   {content}"
                )

            header = f"Search results for: {query}\n"
            header += f"({len(results)} total results, showing top {min(num_results, len(results))})\n"
            header += "-" * 40

            return header + "\n" + "\n\n".join(formatted)

    except httpx.ConnectError:
        return f"Error: Could not connect to SearXNG at {SEARXNG_URI}. Is the service running?"
    except httpx.HTTPStatusError as e:
        return f"Error: SearXNG returned HTTP {e.response.status_code}"
    except Exception as e:
        return f"Error performing web search: {str(e)}"

import os
import re
from urllib.parse import quote, urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from mcp.server import MCPServer


mcp = MCPServer("ChatbreezMCP")

ALLOWED_HOSTS = {"chatbreez.com", "docs.chatbreez.com"}
SITE_ROOTS = ("https://chatbreez.com", "https://docs.chatbreez.com")
API_BASE_URL = "https://api.chatbreez.com"
API_KEY_ENV_VAR = "CHATBREEZ_API_KEY"


async def crawl_chatbreez(start_url: str, max_pages: int = 15) -> str:
    """Crawl Chatbreez's website and docs, up to a maximum number of pages."""
    if not urlparse(start_url).scheme:
        start_url = f"https://{start_url}"

    start_url, _ = urldefrag(start_url)
    parsed_start = urlparse(start_url)
    if parsed_start.scheme not in {"http", "https"} or parsed_start.hostname not in ALLOWED_HOSTS:
        raise ValueError("URL must be on chatbreez.com or docs.chatbreez.com")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    visited = set()
    to_visit = list(SITE_ROOTS)
    if start_url not in to_visit:
        to_visit.append(start_url)
    combined_results = []

    async with httpx.AsyncClient(headers=headers, timeout=10.0, follow_redirects=True) as client:
        while to_visit and len(visited) < max_pages:
            current_url = to_visit.pop(0)

            if current_url in visited:
                continue

            visited.add(current_url)

            try:
                response = await client.get(current_url)
                if response.status_code != 200:
                    continue

                soup = BeautifulSoup(response.text, "html.parser")

                for element in soup(["script", "style", "nav", "footer", "header"]):
                    element.decompose()

                lines = (line.strip() for line in soup.get_text(separator="\n").splitlines())
                clean_text = "\n".join(chunk for chunk in lines if chunk)
                combined_results.append(
                    f"--- PAGE START: {current_url} ---\n{clean_text[:3000]}\n--- PAGE END ---"
                )

                for link in soup.find_all("a", href=True):
                    absolute_url = urljoin(current_url, link["href"])
                    clean_link, _ = urldefrag(absolute_url)
                    parsed_link = urlparse(clean_link)

                    if (
                        parsed_link.scheme in {"http", "https"}
                        and parsed_link.hostname in ALLOWED_HOSTS
                        and clean_link not in visited
                        and clean_link not in to_visit
                    ):
                        to_visit.append(clean_link)

            except httpx.RequestError as exc:
                combined_results.append(f"--- ERROR SCRAPING {current_url}: {exc} ---")

    return "\n\n".join(combined_results)


@mcp.tool()
async def crawl_and_analyze_chatbreez(domain_or_url: str) -> str:
    """
    Crawls up to 15 pages across chatbreez.com and docs.chatbreez.com,
    starting from both homepages and following links between the two sites.
    The provided domain or URL must be on one of these sites.
    """
    scraped_data = await crawl_chatbreez(domain_or_url, max_pages=15)
    return scraped_data[:40000]


async def _send_chatbreez_message(instance_name: str, recipient: str, text: str) -> str:
    api_key = os.environ.get(API_KEY_ENV_VAR, "").strip()
    if not api_key:
        raise ValueError(
            f"Set {API_KEY_ENV_VAR} in the MCP server environment before sending messages."
        )

    instance_name = instance_name.strip()
    if not instance_name:
        raise ValueError("instance_name must not be empty.")
    if not re.fullmatch(r"[0-9]+", recipient):
        raise ValueError("recipient must be an international phone number using digits only, without '+'.")
    if not text.strip():
        raise ValueError("text must not be empty.")

    encoded_instance = quote(instance_name, safe="")
    headers = {"X-API-Key": api_key}
    timeout = httpx.Timeout(15.0)

    try:
        async with httpx.AsyncClient(
            base_url=API_BASE_URL,
            headers=headers,
            timeout=timeout,
        ) as client:
            try:
                status_response = await client.get(
                    f"/whatsapp/connection-state/{encoded_instance}"
                )
                status_response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(
                    "ChatBreez returned HTTP "
                    f"{exc.response.status_code} while checking the instance connection."
                ) from exc

            try:
                status_payload = status_response.json()
            except ValueError as exc:
                raise RuntimeError(
                    "ChatBreez returned an invalid JSON response while checking the instance connection."
                ) from exc

            instance = status_payload.get("instance") if isinstance(status_payload, dict) else None
            state = instance.get("state") if isinstance(instance, dict) else None
            if not isinstance(state, str) or not state:
                raise RuntimeError(
                    "ChatBreez returned an unexpected instance-status response."
                )
            if state != "open":
                raise RuntimeError(
                    f"ChatBreez instance '{instance_name}' is '{state}', not connected. "
                    "Connect or reconnect it from the ChatBreez dashboard before sending."
                )

            try:
                send_response = await client.post(
                    f"/whatsapp/send-text/{encoded_instance}",
                    json={"recipient": recipient, "text": text},
                )
                send_response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(
                    f"ChatBreez returned HTTP {exc.response.status_code} while sending the message."
                ) from exc
    except httpx.RequestError as exc:
        raise RuntimeError("Could not reach the ChatBreez API.") from exc

    return f"Message accepted by ChatBreez for {recipient} using instance '{instance_name}'."


@mcp.tool()
async def send_chatbreez_message(instance_name: str, recipient: str, text: str) -> str:
    """
    Send a WhatsApp text through an instance created and connected in the dashboard.

    Requires CHATBREEZ_API_KEY in the MCP server environment. Recipient numbers
    must include the country code and contain digits only, without a leading '+'.
    """
    return await _send_chatbreez_message(instance_name, recipient, text)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

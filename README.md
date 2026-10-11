# Chatbreez MCP

The `crawl_and_analyze_chatbreez` tool crawls up to 15 pages across
`chatbreez.com` and `docs.chatbreez.com`. It accepts a URL on either site;
both site homepages are included as crawl starting points, and links between
the two sites are followed. URLs on other hosts are rejected.

## Send WhatsApp text messages

Create a ChatBreez account and WhatsApp instance in the
[dashboard](https://chatbreez.com), then scan the generated QR code with the
WhatsApp mobile app to connect it. Generate an API key from the dashboard's API
Keys section.

Configure the MCP server with the API key in its environment. For example:

```json
{
  "mcpServers": {
    "chatbreez": {
      "command": "chatbreez-mcp",
      "env": {
        "CHATBREEZ_API_KEY": "your_api_key"
      }
    }
  }
}
```

Use the `send_chatbreez_message` tool with:

- `instance_name`: the instance name from the ChatBreez dashboard.
- `recipient`: the destination WhatsApp number with country code, digits only
  and without a leading `+` (for example, `254700000000`).
- `text`: the message body.

Before sending, the server checks the instance's connection state and only
sends when ChatBreez reports it as connected. Instance creation and QR linking
remain dashboard actions. The documented API does not provide a way to list
connected instances, so the instance name must be supplied to the tool.

Run the MCP server with:

```sh
chatbreez-mcp
```
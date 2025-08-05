import aiohttp
import json
import base64

class SimpleMCPClient:
    """
    Simple client for communicating with an MCP server using JSON-RPC over SSE.
    """
    def __init__(self, config: dict, smithery_api_key: str, base_url: str):
        """
        Args:
            config: Configuration dict for the MCP server, will be JSON-encoded and base64-encoded.
            smithery_api_key: API key for the MCP server.
            base_url: Base URL of the MCP server endpoint (without /mcp?query params).
        """
        self.config_b64 = base64.b64encode(json.dumps(config).encode()).decode()
        self.smithery_api_key = smithery_api_key
        self.base_url = base_url.rstrip('/')
        self.request_id = 0
        self.session_id = None
        self.session = None

    def get_next_id(self) -> int:
        self.request_id += 1
        return self.request_id

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _send_request(self, method: str, params: dict = None) -> dict:
        url = f"{self.base_url}/mcp?config={self.config_b64}&api_key={self.smithery_api_key}"
        payload = {
            "jsonrpc": "2.0",
            "id": self.get_next_id(),
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id

        async with self.session.post(url, json=payload, headers=headers) as response:
            if "mcp-session-id" in response.headers:
                self.session_id = response.headers["mcp-session-id"]
            async for line in response.content:
                text = line.decode().strip()
                if text.startswith("data: "):
                    data = text[6:]
                    try:
                        return json.loads(data)
                    except json.JSONDecodeError:
                        continue
        return {}

    async def initialize(self) -> bool:
        """
        Initialize the MCP session. Returns True if successful.
        """
        resp = await self._send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "simple-client", "version": "1.0.0"},
            },
        )
        return bool(resp and "result" in resp)

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """
        Call a named tool via the MCP server.
        Returns the 'result' portion of the response.
        """
        resp = await self._send_request(
            "tools/call", {"name": tool_name, "arguments": arguments}
        )
        if resp and "result" in resp:
            return resp["result"]
        error = resp.get("error", {}).get("message") if isinstance(resp, dict) else None
        raise RuntimeError(f"MCP tool call failed: {error or resp}")
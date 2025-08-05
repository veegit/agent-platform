import aiohttp
import json
import base64
import asyncio
from datetime import datetime, timedelta

class SimpleMCPClient:
    def __init__(self, config, smithery_api_key):
        self.config_b64 = base64.b64encode(json.dumps(config).encode()).decode()
        self.smithery_api_key = smithery_api_key
        self.base_url = "https://server.smithery.ai/@campertunity/mcp-server"
        self.request_id = 0
        self.session_id = None
        self.session = None
        
    def get_next_id(self):
        self.request_id += 1
        return self.request_id

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _send_request(self, method, params=None):
        url = f"{self.base_url}/mcp?config={self.config_b64}&api_key={self.smithery_api_key}"
        
        request_payload = {
            "jsonrpc": "2.0",
            "id": self.get_next_id(),
            "method": method
        }
        if params:
            request_payload["params"] = params
        
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "Cache-Control": "no-cache"
        }
        
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
        
        async with self.session.post(url, json=request_payload, headers=headers) as response:
            if 'mcp-session-id' in response.headers:
                self.session_id = response.headers['mcp-session-id']
            
            # Read SSE response
            async for line in response.content:
                decoded_line = line.decode('utf-8').strip()
                if decoded_line.startswith('data: '):
                    data_part = decoded_line[6:]
                    try:
                        return json.loads(data_part)
                    except json.JSONDecodeError:
                        continue
        return None

    async def initialize(self):
        response = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "simple-client", "version": "1.0.0"}
        })
        return response and "result" in response

    async def search_places(self, latitude, longitude, start_date, end_date):
        response = await self._send_request("tools/call", {
            "name": "place-search",
            "arguments": {
                "latitude": latitude,
                "longitude": longitude,
                "startDate": start_date,
                "endDate": end_date,
                "radius": 200
            }
        })
        
        if response and "result" in response:
            return response["result"]
        elif response and "error" in response:
            print(f"Error: {response['error']['message']}")
        return None

async def main():
    config = {
        "campertunityApiKey": "a94435e25cef47a1099e1daef48926158755e133c0da3ca4"
    }
    smithery_api_key = "90f5c1d0-b194-4083-9225-a699a69ce044"
    
    # Calculate dates: 1 week and 2 weeks from today
    today = datetime.now()
    start_date = (today + timedelta(weeks=1)).strftime("%Y-%m-%d")
    end_date = (today + timedelta(weeks=2)).strftime("%Y-%m-%d")
    
    # Coordinates: 51.190012693525944, -115.51663014428922
    latitude = 51.190012693525944
    longitude = -115.51663014428922
    
    print(f"Searching for places near ({latitude}, {longitude}) within 200 KM radius")
    print(f"Dates: {start_date} to {end_date}")
    
    async with SimpleMCPClient(config, smithery_api_key) as client:
        if await client.initialize():
            result = await client.search_places(latitude, longitude, start_date, end_date)
            
            if result:
                print(f"\n✅ Search completed successfully!")
                print(f"Response: {json.dumps(result, indent=2)}")
            else:
                print("❌ No results found")
        else:
            print("❌ Failed to initialize")

if __name__ == "__main__":
    asyncio.run(main())


"""
TED (Tenders Electronic Daily) API Client
"""
import aiohttp

class TEDClient:
    def __init__(self, api_key):
        if not api_key:
            raise ValueError("TED API-Key fehlt!")
        self.api_key = api_key
        self.base_url = "https://ted.europa.eu/api/v3.0"

    async def search(self, params):
        """Führt eine Suche in der TED API durch und gibt eine Ergebnisliste zurück."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }
        query = {
            "query": f'(ND=[{params["q"]}] OR TI=[{params["q"]}]) AND PD=[{params["publishedFrom"]} TO {params["publishedTo"]}] AND VA>=[{params["minValue"]}] AND DS=[CONTRACT_NOTICE]',
            "fields": ["ND", "TI", "PD", "TD", "VA", "CU", "CY", "AN"],
            "limit": 100,
            "page": 1
        }
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(f"{self.base_url}/notices/search", json=query) as resp:
                data = await resp.json()
                results = []
                for item in data.get("results", []):
                    results.append({
                        "api": "ted",
                        "id": item.get("ND", [""])[0],
                        "title": item.get("TI", [""])[0],
                        "publish_date": item.get("PD", [""])[0],
                        "deadline": item.get("TD", [""])[0] if item.get("TD") else "",
                        "value": item.get("VA", [""])[0] if item.get("VA") else "",
                        "currency": item.get("CU", [""])[0] if item.get("CU") else "",
                        "country": item.get("CY", [""])[0] if item.get("CY") else "",
                        "organization": item.get("AN", [""])[0] if item.get("AN") else "",
                        "url": f'https://ted.europa.eu/udl?uri=TED:NOTICE:{item.get("ND", [""])[0]}'
                    })
                return results

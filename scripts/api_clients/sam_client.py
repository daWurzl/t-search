"""
SAM.gov API Client
"""
import aiohttp

class SAMClient:
    def __init__(self, api_key):
        if not api_key:
            raise ValueError("SAM.gov API-Key fehlt!")
        self.api_key = api_key
        self.base_url = "https://api.sam.gov/prod/opportunities/v2/search"

    async def search(self, params):
        """Führt eine Suche in SAM.gov durch und gibt eine Ergebnisliste zurück."""
        headers = {
            "Accept": "application/json"
        }
        query = {
            "api_key": self.api_key,
            "keywords": params["keyword"],
            "postedFrom": params["postedFrom"],
            "postedTo": params["postedTo"],
            "noticeType": "Presolicitation,Combined Synopsis/Solicitation,Solicitation",
            "limit": 100
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(self.base_url, params=query, headers=headers) as resp:
                data = await resp.json()
                results = []
                for item in data.get("opportunitiesData", []):
                    results.append({
                        "api": "sam",
                        "id": item.get("noticeId", ""),
                        "title": item.get("title", ""),
                        "publish_date": item.get("postedDate", ""),
                        "deadline": item.get("responseDeadLine", ""),
                        "value": item.get("award", {}).get("amount", ""),
                        "currency": "USD",
                        "country": item.get("placeOfPerformance", {}).get("countryCode", ""),
                        "organization": item.get("department", ""),
                        "url": item.get("solicitationURL", "")
                    })
                return results

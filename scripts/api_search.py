#!/usr/bin/env python3
"""
Sucht Ausschreibungen über TED und SAM.gov APIs und speichert die Ergebnisse.
"""

import os
import sys
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

# Importiere die API-Clients
from api_clients.ted_client import TEDClient
from api_clients.sam_client import SAMClient

RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)

def get_search_params():
    """Liest die Suchparameter aus Umgebungsvariablen."""
    return {
        "search_term": os.getenv("SEARCH_TERM", ""),
        "apis": [api.strip() for api in os.getenv("APIS", "ted,sam").split(",")],
        "date_from": os.getenv("DATE_FROM") or (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
        "date_to": os.getenv("DATE_TO") or datetime.now().strftime("%Y-%m-%d"),
        "min_value": int(os.getenv("MIN_VALUE", "0"))
    }

async def main():
    params = get_search_params()
    results = []

    # TED API
    if "ted" in params["apis"]:
        print("Suche in TED...")
        ted_client = TEDClient(api_key=os.getenv("TED_API_KEY"))
        ted_results = await ted_client.search({
            "q": params["search_term"],
            "publishedFrom": params["date_from"],
            "publishedTo": params["date_to"],
            "minValue": params["min_value"]
        })
        results.extend(ted_results)

    # SAM.gov API
    if "sam" in params["apis"]:
        print("Suche in SAM.gov...")
        sam_client = SAMClient(api_key=os.getenv("SAM_GOV_API_KEY"))
        sam_results = await sam_client.search({
            "keyword": params["search_term"],
            "postedFrom": params["date_from"],
            "postedTo": params["date_to"],
            "minValue": params["min_value"]
        })
        results.extend(sam_results)

    # Ergebnisse speichern
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = RESULTS_DIR / f"search_results_{timestamp}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"{len(results)} Ergebnisse gespeichert in {out_file}")

if __name__ == "__main__":
    asyncio.run(main())

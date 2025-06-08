#!/usr/bin/env python3
"""
Erstellt eine kurze Zusammenfassung der letzten Suchergebnisse.
"""
import json
from pathlib import Path

def main():
    results_dir = Path("results")
    result_files = sorted(results_dir.glob("search_results_*.json"), reverse=True)
    if not result_files:
        print("Keine Ergebnisse gefunden.")
        return
    with open(result_files[0], "r", encoding="utf-8") as f:
        results = json.load(f)
    print(f"### Ergebnisse ({len(results)})")
    apis = set(r.get("api") for r in results)
    for api in apis:
        count = sum(1 for r in results if r.get("api") == api)
        print(f"- {api}: {count} Treffer")

if __name__ == "__main__":
    main()

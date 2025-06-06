#!/usr/bin/env python3
"""
Generiert eine Zusammenfassung der Suchergebnisse für GitHub Actions Summary
"""

import json
import os
from pathlib import Path
from datetime import datetime

def generate_summary():
    """Generiert eine Markdown-Zusammenfassung der neuesten Suchergebnisse"""
    
    results_dir = Path('results')
    if not results_dir.exists():
        print("Keine Ergebnisse verfügbar.")
        return
    
    # Neueste Ergebnisdatei finden
    result_files = list(results_dir.glob('search_results_*.json'))
    if not result_files:
        print("Keine Suchergebnisse gefunden.")
        return
    
    latest_file = max(result_files, key=lambda x: x.stat().st_mtime)
    
    try:
        with open(latest_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
        
        metadata = results.get('search_metadata', {})
        stats = results.get('statistics', {})
        errors = results.get('errors', [])
        
        print(f"### ✅ Suche erfolgreich abgeschlossen")
        print(f"**Suchbegriff:** {metadata.get('search_term', 'N/A')}")
        print(f"**Durchsuchte APIs:** {', '.join(metadata.get('apis_used', []))}")
        print(f"**Zeitraum:** {metadata.get('date_from', 'N/A')} bis {metadata.get('date_to', 'N/A')}")
        print()
        
        print(f"### 📊 Ergebnisse")
        print(f"**Gesamtanzahl:** {stats.get('total_count', 0)} Ausschreibungen")
        print()
        
        # API-Aufschlüsselung
        api_breakdown = stats.get('api_breakdown', {})
        if api_breakdown:
            print("**Pro API:**")
            for api, count in api_breakdown.items():
                print(f"- {api.upper()}: {count} Ergebnisse")
            print()
        
        # Wert-Statistiken
        value_stats = stats.get('value_statistics', {})
        if value_stats:
            print("**Auftragswerte:**")
            print(f"- Gesamtwert: €{value_stats.get('total_value', 0):,.2f}")
            print(f"- Durchschnitt: €{value_stats.get('average_value', 0):,.2f}")
            print(f"- Höchster Wert: €{value_stats.get('max_value', 0):,.2f}")
            print()
        
        # Top-Länder
        country_breakdown = stats.get('country_breakdown', {})
        if country_breakdown:
            print("**Top 5 Länder:**")
            for country, count in list(country_breakdown.items())[:5]:
                print(f"- {country}: {count} Ausschreibungen")
            print()
        
        # Fehler-Report
        if errors:
            print("### ⚠️ Aufgetretene Probleme")
            for error in errors:
                print(f"- **{error.get('api', 'Unknown')}:** {error.get('error', 'Unbekannter Fehler')}")
            print()
        
        print(f"📁 **Ergebnisdateien:** JSON, CSV und Excel verfügbar zum Download")
        
    except Exception as e:
        print(f"❌ Fehler beim Generieren der Zusammenfassung: {str(e)}")

if __name__ == "__main__":
    generate_summary()

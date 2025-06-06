#!/usr/bin/env python3
"""
Hauptskript für die API-Suche über alle konfigurierten öffentlichen Ausschreibungs-APIs
Koordiniert die Suche über TED, OpenOpps, SAM.gov und Contracts Finder APIs
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path

# Lokale Module importieren
from api_clients.ted_client import TEDClient
from api_clients.openopps_client import OpenOppsClient
from api_clients.sam_client import SAMClient
from api_clients.contracts_finder_client import ContractsFinderClient
from utils.data_processor import DataProcessor
from utils.logger import setup_logging

class APISearchCoordinator:
    """
    Koordiniert die Suche über alle konfigurierten APIs und konsolidiert die Ergebnisse
    """
    
    def __init__(self):
        """Initialisiert den Search Coordinator mit allen verfügbaren API-Clients"""
        self.setup_environment()
        self.logger = setup_logging()
        
        # API-Clients initialisieren
        self.clients = {
            'ted': TEDClient(api_key=os.getenv('TED_API_KEY')),
            'openopps': OpenOppsClient(
                username=os.getenv('OPENOPPS_USERNAME'),
                password=os.getenv('OPENOPPS_PASSWORD')
            ),
            'sam': SAMClient(api_key=os.getenv('SAM_GOV_API_KEY')),
            'contracts_finder': ContractsFinderClient()
        }
        
        # Datenverarbeitungskomponente
        self.data_processor = DataProcessor()
        
        # Ergebnisverzeichnis erstellen
        self.results_dir = Path('results')
        self.results_dir.mkdir(exist_ok=True)
        
        self.logger.info("API Search Coordinator initialisiert")

    def setup_environment(self):
        """Konfiguriert die Umgebungsvariablen und Verzeichnisstruktur"""
        # Erforderliche Verzeichnisse erstellen
        os.makedirs('results', exist_ok=True)
        os.makedirs('logs', exist_ok=True)
        os.makedirs('cache', exist_ok=True)

    async def execute_search(self) -> Dict[str, Any]:
        """
        Führt die koordinierte Suche über alle ausgewählten APIs durch
        
        Returns:
            Dict mit konsolidierten Suchergebnissen und Metadaten
        """
        search_params = self.parse_search_parameters()
        self.logger.info(f"Starte Suche mit Parametern: {search_params}")
        
        results = {
            'search_metadata': {
                'search_term': search_params['search_term'],
                'apis_used': search_params['apis'],
                'date_from': search_params['date_from'],
                'date_to': search_params['date_to'],
                'min_value': search_params['min_value'],
                'search_timestamp': datetime.now().isoformat(),
                'search_id': self.generate_search_id()
            },
            'api_results': {},
            'consolidated_results': [],
            'statistics': {},
            'errors': []
        }
        
        # Parallele API-Aufrufe durchführen
        search_tasks = []
        for api_name in search_params['apis']:
            if api_name in self.clients:
                task = self.search_single_api(api_name, search_params)
                search_tasks.append((api_name, task))
            else:
                self.logger.warning(f"Unbekannte API: {api_name}")
        
        # Auf alle API-Antworten warten
        for api_name, task in search_tasks:
            try:
                api_results = await task
                results['api_results'][api_name] = api_results
                self.logger.info(f"API {api_name}: {len(api_results.get('tenders', []))} Ergebnisse gefunden")
                
            except Exception as e:
                error_msg = f"Fehler bei API {api_name}: {str(e)}"
                self.logger.error(error_msg)
                results['errors'].append({
                    'api': api_name,
                    'error': error_msg,
                    'timestamp': datetime.now().isoformat()
                })
        
        # Ergebnisse konsolidieren und normalisieren
        results['consolidated_results'] = await self.consolidate_results(results['api_results'])
        results['statistics'] = self.calculate_statistics(results['consolidated_results'])
        
        # Ergebnisse speichern
        await self.save_results(results)
        
        self.logger.info(f"Suche abgeschlossen. {len(results['consolidated_results'])} Ergebnisse gefunden.")
        return results

    async def search_single_api(self, api_name: str, search_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Führt die Suche für eine einzelne API durch
        
        Args:
            api_name: Name der API (ted, openopps, sam, contracts_finder)
            search_params: Normalisierte Suchparameter
            
        Returns:
            Dict mit API-spezifischen Ergebnissen
        """
        client = self.clients[api_name]
        self.logger.info(f"Starte Suche für API: {api_name}")
        
        try:
            # API-spezifische Parameterkonvertierung
            api_params = self.convert_params_for_api(api_name, search_params)
            
            # Suche durchführen
            results = await client.search(api_params)
            
            # Ergebnisse validieren und normalisieren
            normalized_results = self.data_processor.normalize_api_results(api_name, results)
            
            return {
                'api': api_name,
                'success': True,
                'tenders': normalized_results,
                'raw_count': len(results.get('data', [])),
                'normalized_count': len(normalized_results),
                'search_time': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"API {api_name} Fehler: {str(e)}")
            return {
                'api': api_name,
                'success': False,
                'error': str(e),
                'tenders': [],
                'search_time': datetime.now().isoformat()
            }

    def convert_params_for_api(self, api_name: str, search_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Konvertiert die standardisierten Suchparameter in API-spezifische Parameter
        
        Args:
            api_name: Name der API
            search_params: Standardisierte Suchparameter
            
        Returns:
            API-spezifische Parameter
        """
        base_params = {
            'query': search_params['search_term'],
            'date_from': search_params['date_from'],
            'date_to': search_params['date_to'],
            'min_value': search_params['min_value']
        }
        
        # API-spezifische Anpassungen
        if api_name == 'ted':
            return {
                'q': search_params['search_term'],
                'publishedFrom': search_params['date_from'],
                'publishedTo': search_params['date_to'],
                'minValue': search_params['min_value']
            }
        elif api_name == 'openopps':
            return {
                'search': search_params['search_term'],
                'releasedate__gte': search_params['date_from'],
                'releasedate__lte': search_params['date_to'],
                'min_amount': search_params['min_value']
            }
        elif api_name == 'sam':
            return {
                'keyword': search_params['search_term'],
                'postedFrom': search_params['date_from'],
                'postedTo': search_params['date_to'],
                'minValue': search_params['min_value'],
                'ptype': 'o'  # Opportunities
            }
        elif api_name == 'contracts_finder':
            return {
                'keyword': search_params['search_term'],
                'publishedFrom': search_params['date_from'],
                'publishedTo': search_params['date_to'],
                'minValue': search_params['min_value']
            }
        
        return base_params

    async def consolidate_results(self, api_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Konsolidiert und dedupliziert Ergebnisse von allen APIs
        
        Args:
            api_results: Dictionary mit Ergebnissen von allen APIs
            
        Returns:
            Liste mit konsolidierten, normalisierten Ausschreibungen
        """
        all_tenders = []
        
        for api_name, api_result in api_results.items():
            if api_result.get('success', False):
                tenders = api_result.get('tenders', [])
                
                # API-Identifikation zu jedem Ergebnis hinzufügen
                for tender in tenders:
                    tender['source_api'] = api_name
                    tender['search_relevance'] = self.calculate_relevance_score(tender)
                
                all_tenders.extend(tenders)
        
        # Duplikate entfernen basierend auf Titel und Organisation
        deduplicated = self.data_processor.remove_duplicates(all_tenders)
        
        # Nach Relevanz und Datum sortieren
        sorted_results = sorted(deduplicated, 
                              key=lambda x: (x.get('search_relevance', 0), x.get('publish_date', '')), 
                              reverse=True)
        
        return sorted_results

    def calculate_relevance_score(self, tender: Dict[str, Any]) -> float:
        """
        Berechnet einen Relevanz-Score für eine Ausschreibung basierend auf Suchbegriff-Matching
        
        Args:
            tender: Ausschreibungsdaten
            
        Returns:
            Relevanz-Score zwischen 0 und 1
        """
        search_term = self.parse_search_parameters()['search_term'].lower()
        
        score = 0.0
        
        # Titel-Matching (höchste Gewichtung)
        title = tender.get('title', '').lower()
        if search_term in title:
            score += 0.5
        
        # Beschreibung-Matching
        description = tender.get('description', '').lower()
        if search_term in description:
            score += 0.3
        
        # Organisation-Matching
        organization = tender.get('organization', '').lower()
        if search_term in organization:
            score += 0.2
        
        return min(score, 1.0)

    def calculate_statistics(self, consolidated_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Berechnet Statistiken über die gefundenen Ausschreibungen
        
        Args:
            consolidated_results: Liste der konsolidierten Ergebnisse
            
        Returns:
            Dictionary mit verschiedenen Statistiken
        """
        if not consolidated_results:
            return {
                'total_count': 0,
                'api_breakdown': {},
                'value_statistics': {},
                'country_breakdown': {},
                'date_range': {}
            }
        
        # Basis-Statistiken
        stats = {
            'total_count': len(consolidated_results),
            'api_breakdown': {},
            'value_statistics': {},
            'country_breakdown': {},
            'date_range': {}
        }
        
        # API-Aufschlüsselung
        api_counts = {}
        for tender in consolidated_results:
            api = tender.get('source_api', 'unknown')
            api_counts[api] = api_counts.get(api, 0) + 1
        stats['api_breakdown'] = api_counts
        
        # Wert-Statistiken
        values = [tender.get('value', 0) for tender in consolidated_results if tender.get('value', 0) > 0]
        if values:
            stats['value_statistics'] = {
                'total_value': sum(values),
                'average_value': sum(values) / len(values),
                'min_value': min(values),
                'max_value': max(values),
                'count_with_value': len(values)
            }
        
        # Länder-Aufschlüsselung
        country_counts = {}
        for tender in consolidated_results:
            country = tender.get('country', 'unknown')
            country_counts[country] = country_counts.get(country, 0) + 1
        stats['country_breakdown'] = dict(sorted(country_counts.items(), 
                                                key=lambda x: x[1], reverse=True))
        
        # Datumsbereich
        dates = [tender.get('publish_date') for tender in consolidated_results 
                if tender.get('publish_date')]
        if dates:
            stats['date_range'] = {
                'earliest': min(dates),
                'latest': max(dates)
            }
        
        return stats

    async def save_results(self, results: Dict[str, Any]) -> None:
        """
        Speichert die Suchergebnisse in verschiedenen Formaten
        
        Args:
            results: Komplette Suchergebnisse mit Metadaten
        """
        search_id = results['search_metadata']['search_id']
        
        # JSON-Format speichern (vollständige Daten)
        json_file = self.results_dir / f'search_results_{search_id}.json'
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        
        # CSV-Format speichern (konsolidierte Ergebnisse)
        csv_file = self.results_dir / f'search_results_{search_id}.csv'
        await self.data_processor.save_to_csv(results['consolidated_results'], csv_file)
        
        # Excel-Format speichern (mit mehreren Arbeitsblättern)
        excel_file = self.results_dir / f'search_results_{search_id}.xlsx'
        await self.data_processor.save_to_excel(results, excel_file)
        
        # Zusammenfassung als Markdown speichern
        summary_file = self.results_dir / f'search_summary_{search_id}.md'
        await self.save_summary_markdown(results, summary_file)
        
        self.logger.info(f"Ergebnisse gespeichert: {json_file}, {csv_file}, {excel_file}, {summary_file}")

    async def save_summary_markdown(self, results: Dict[str, Any], file_path: Path) -> None:
        """
        Speichert eine Zusammenfassung der Suchergebnisse als Markdown
        
        Args:
            results: Suchergebnisse
            file_path: Pfad für die Markdown-Datei
        """
        metadata = results['search_metadata']
        stats = results['statistics']
        
        summary = f"""# Ausschreibungssuche - Zusammenfassung

## Suchparameter
- **Suchbegriff:** {metadata['search_term']}
- **APIs:** {', '.join(metadata['apis_used'])}
- **Zeitraum:** {metadata['date_from']} bis {metadata['date_to']}
- **Mindestauftragswert:** {metadata['min_value']} EUR
- **Suche durchgeführt:** {metadata['search_timestamp']}

## Ergebnisse
- **Gesamtanzahl:** {stats.get('total_count', 0)} Ausschreibungen gefunden

### API-Aufschlüsselung
"""
        
        for api, count in stats.get('api_breakdown', {}).items():
            summary += f"- **{api.upper()}:** {count} Ergebnisse\n"
        
        if stats.get('value_statistics'):
            val_stats = stats['value_statistics']
            summary += f"""
### Wert-Statistiken
- **Gesamtwert:** {val_stats['total_value']:,.2f} EUR
- **Durchschnittswert:** {val_stats['average_value']:,.2f} EUR
- **Höchster Wert:** {val_stats['max_value']:,.2f} EUR
- **Niedrigster Wert:** {val_stats['min_value']:,.2f} EUR
"""
        
        if stats.get('country_breakdown'):
            summary += "\n### Länder-Verteilung\n"
            for country, count in list(stats['country_breakdown'].items())[:10]:
                summary += f"- **{country}:** {count} Ausschreibungen\n"
        
        if results.get('errors'):
            summary += "\n### Fehler und Warnungen\n"
            for error in results['errors']:
                summary += f"- **{error['api']}:** {error['error']}\n"
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(summary)

    def parse_search_parameters(self) -> Dict[str, Any]:
        """
        Parst die Suchparameter aus Umgebungsvariablen
        
        Returns:
            Dictionary mit standardisierten Suchparametern
        """
        search_term = os.getenv('SEARCH_TERM', '').strip()
        if not search_term:
            raise ValueError("SEARCH_TERM ist erforderlich")
        
        # APIs aus komma-getrennter Liste parsen
        apis_str = os.getenv('APIS', 'ted,openopps,sam,contracts_finder')
        apis = [api.strip() for api in apis_str.split(',') if api.strip()]
        
        # Datumsbereich parsen
        date_from = os.getenv('DATE_FROM')
        date_to = os.getenv('DATE_TO')
        
        # Standardwerte setzen falls nicht angegeben
        if not date_from:
            date_from = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        if not date_to:
            date_to = datetime.now().strftime('%Y-%m-%d')
        
        # Mindestauftragswert parsen
        min_value = int(os.getenv('MIN_VALUE', '0'))
        
        return {
            'search_term': search_term,
            'apis': apis,
            'date_from': date_from,
            'date_to': date_to,
            'min_value': min_value
        }

    def generate_search_id(self) -> str:
        """
        Generiert eine eindeutige ID für die Suche
        
        Returns:
            Eindeutige Suche-ID
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return f"search_{timestamp}"

async def main():
    """
    Hauptfunktion - führt die koordinierte API-Suche durch
    """
    try:
        coordinator = APISearchCoordinator()
        results = await coordinator.execute_search()
        
        print(f"Suche erfolgreich abgeschlossen!")
        print(f"Gefundene Ausschreibungen: {len(results['consolidated_results'])}")
        print(f"Verwendete APIs: {', '.join(results['search_metadata']['apis_used'])}")
        
        if results['errors']:
            print(f"Aufgetretene Fehler: {len(results['errors'])}")
            for error in results['errors']:
                print(f"  - {error['api']}: {error['error']}")
        
        return 0
        
    except Exception as e:
        print(f"Kritischer Fehler: {str(e)}")
        logging.exception("Unbehandelter Fehler in main()")
        return 1

if __name__ == "__main__":
    # Asyncio Event Loop starten
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

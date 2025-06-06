"""
TED (Tenders Electronic Daily) API Client
Implementiert die Schnittstelle zur europäischen öffentlichen Ausschreibungsplattform
"""

import aiohttp
import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import json

class TEDClient:
    """
    Client für die TED (Tenders Electronic Daily) API der Europäischen Union
    Dokumentation: https://docs.ted.europa.eu/api/index.html
    """
    
    def __init__(self, api_key: str):
        """
        Initialisiert den TED API Client
        
        Args:
            api_key: TED API-Schlüssel (über EU Login Portal generiert)
        """
        if not api_key:
            raise ValueError("TED API-Schlüssel ist erforderlich")
        
        self.api_key = api_key
        self.base_url = "https://ted.europa.eu/api/v3.0"
        self.session = None
        self.logger = logging.getLogger(__name__)
        
        # Standard-Headers für alle Anfragen
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'PublicTenderSearch/1.0'
        }

    async def __aenter__(self):
        """Async Context Manager - erstellt HTTP-Session"""
        self.session = aiohttp.ClientSession(
            headers=self.headers,
            timeout=aiohttp.ClientTimeout(total=300)  # 5 Minuten Timeout
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async Context Manager - schließt HTTP-Session"""
        if self.session:
            await self.session.close()

    async def search(self, search_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Führt eine Suche in der TED-Datenbank durch
        
        Args:
            search_params: Suchparameter
                - q: Suchquery (erforderlich)
                - publishedFrom: Startdatum (YYYY-MM-DD)
                - publishedTo: Enddatum (YYYY-MM-DD)
                - minValue: Mindestauftragswert
                - limit: Maximale Anzahl Ergebnisse (Standard: 100)
                
        Returns:
            Dictionary mit Suchergebnissen und Metadaten
        """
        async with self:
            return await self._execute_search(search_params)

    async def _execute_search(self, search_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Interne Methode zur Durchführung der TED API-Suche
        """
        self.logger.info(f"TED API Suche gestartet: {search_params.get('q', '')}")
        
        # Suchquery für TED-API konstruieren
        search_query = self._build_search_query(search_params)
        
        # API-Request-Body zusammenstellen
        request_body = {
            "query": search_query,
            "fields": self._get_response_fields(),
            "limit": search_params.get('limit', 100),
            "page": 1,
            "scope": "latest"  # Nur neueste Versionen
        }
        
        all_results = []
        page = 1
        max_pages = 10  # Begrenzung zur Sicherheit
        
        try:
            while page <= max_pages:
                request_body["page"] = page
                
                async with self.session.post(
                    f"{self.base_url}/notices/search",
                    json=request_body
                ) as response:
                    
                    if response.status == 401:
                        raise Exception("TED API: Ungültiger API-Schlüssel")
                    elif response.status == 429:
                        # Rate Limiting - kurz warten und erneut versuchen
                        await asyncio.sleep(2)
                        continue
                    elif response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"TED API Fehler {response.status}: {error_text}")
                    
                    data = await response.json()
                    
                    # Ergebnisse aus der aktuellen Seite extrahieren
                    page_results = data.get('results', [])
                    if not page_results:
                        break  # Keine weiteren Ergebnisse
                    
                    all_results.extend(page_results)
                    
                    # Prüfen ob weitere Seiten verfügbar sind
                    total_results = data.get('total', 0)
                    current_count = len(all_results)
                    
                    if current_count >= total_results:
                        break  # Alle Ergebnisse geladen
                    
                    page += 1
                    
                    # Kurze Pause zwischen Requests
                    await asyncio.sleep(0.5)
            
            self.logger.info(f"TED API: {len(all_results)} Ergebnisse gefunden")
            
            return {
                'success': True,
                'total_count': len(all_results),
                'data': all_results,
                'api': 'ted',
                'query_used': search_query
            }
            
        except Exception as e:
            self.logger.error(f"TED API Fehler: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'data': [],
                'api': 'ted'
            }

    def _build_search_query(self, params: Dict[str, Any]) -> str:
        """
        Konstruiert die Suchquery für die TED-API basierend auf den Parametern
        
        Args:
            params: Suchparameter
            
        Returns:
            TED-API kompatible Suchquery
        """
        query_parts = []
        
        # Hauptsuchbegriff
        search_term = params.get('q', '').strip()
        if search_term:
            # Suche in Titel und Beschreibung
            query_parts.append(f'(ND=[{search_term}] OR TI=[{search_term}])')
        
        # Datumsfilter
        date_from = params.get('publishedFrom')
        date_to = params.get('publishedTo')
        
        if date_from and date_to:
            query_parts.append(f'PD=[{date_from} TO {date_to}]')
        elif date_from:
            query_parts.append(f'PD>=[{date_from}]')
        elif date_to:
            query_parts.append(f'PD<=[{date_to}]')
        
        # Mindestauftragswert
        min_value = params.get('minValue')
        if min_value and int(min_value) > 0:
            query_parts.append(f'VA>=[{min_value}]')
        
        # Nur aktive Ausschreibungen (nicht archiviert)
        query_parts.append('DS=[CONTRACT_NOTICE]')
        
        # Query zusammenfügen
        if query_parts:
            return ' AND '.join(query_parts)
        else:
            return '*'  # Fallback: alle Ergebnisse

    def _get_response_fields(self) -> List[str]:
        """
        Definiert welche Felder in der API-Antwort enthalten sein sollen
        
        Returns:
            Liste der angeforderten Felder
        """
        return [
            'ND',      # Notice Document (Ausschreibungsdokument)
            'TI',      # Title (Titel)
            'PD',      # Publication Date (Veröffentlichungsdatum)
            'DD',      # Document Date (Dokumentdatum)
            'TD',      # Tender Deadline (Einreichungsfrist)
            'OJ',      # Official Journal (Amtsblatt-Referenz)
            'RC',      # Reference Code (Referenzcode)
            'TY',      # Document Type (Dokumenttyp)
            'PR',      # Procedure (Verfahrensart)
            'AC',      # Award Criteria (Zuschlagskriterien)
            'PC',      # Procurement Category (Beschaffungskategorie)
            'VA',      # Value Amount (Auftragswert)
            'CU',      # Currency (Währung)
            'CY',      # Country (Land)
            'TW',      # Town (Stadt)
            'AU',      # Authority (Vergabestelle)
            'AN',      # Authority Name (Name der Vergabestelle)
            'IA',      # Internet Address (Webadresse)
            'CPV',     # Common Procurement Vocabulary (CPV-Code)
            'NC'       # NUTS Code (Geografischer Code)
        ]

    async def get_notice_details(self, notice_id: str) -> Optional[Dict[str, Any]]:
        """
        Ruft die Details einer spezifischen Ausschreibung ab
        
        Args:
            notice_id: TED-Notice-ID
            
        Returns:
            Detaillierte Ausschreibungsdaten oder None bei Fehler
        """
        try:
            async with self:
                async with self.session.get(
                    f"{self.base_url}/notices/{notice_id}"
                ) as response:
                    
                    if response.status == 200:
                        return await response.json()
                    else:
                        self.logger.warning(f"TED API: Notice {notice_id} nicht gefunden")
                        return None
                        
        except Exception as e:
            self.logger.error(f"Fehler beim Abrufen der Notice {notice_id}: {str(e)}")
            return None

    def normalize_result(self, raw_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalisiert ein TED-API-Ergebnis in das Standard-Format
        
        Args:
            raw_result: Rohe API-Antwort
            
        Returns:
            Normalisiertes Ergebnis
        """
        try:
            # Grundlegende Felder extrahieren
            title = raw_result.get('TI', [''])[0] if raw_result.get('TI') else 'Unbekannter Titel'
            
            # Datum-Felder normalisieren
            publish_date = self._extract_date(raw_result.get('PD'))
            deadline = self._extract_date(raw_result.get('TD'))
            
            # Auftragswert extrahieren
            value, currency = self._extract_value(raw_result.get('VA'), raw_result.get('CU'))
            
            # Geografische Informationen
            country = raw_result.get('CY', [''])[0] if raw_result.get('CY') else 'EU'
            city = raw_result.get('TW', [''])[0] if raw_result.get('TW') else ''
            
            # Organisation/Vergabestelle
            organization = raw_result.get('AN', [''])[0] if raw_result.get('AN') else ''
            if not organization:
                organization = raw_result.get('AU', [''])[0] if raw_result.get('AU') else 'Unbekannte Organisation'
            
            # URL zur Ausschreibung
            url = f"https://ted.europa.eu/udl?uri=TED:NOTICE:{raw_result.get('ND', [''])[0]}"
            
            # CPV-Codes für Kategorisierung
            cpv_codes = raw_result.get('CPV', [])
            
            return {
                'id': raw_result.get('ND', [''])[0],
                'title': title,
                'description': title,  # TED liefert oft keine separate Beschreibung
                'organization': organization,
                'value': value,
                'currency': currency,
                'publish_date': publish_date,
                'deadline': deadline,
                'country': country,
                'city': city,
                'url': url,
                'cpv_codes': cpv_codes,
                'source_api': 'ted',
                'document_type': raw_result.get('TY', [''])[0] if raw_result.get('TY') else '',
                'reference_code': raw_result.get('RC', [''])[0] if raw_result.get('RC') else ''
            }
            
        except Exception as e:
            self.logger.error(f"Fehler bei TED-Ergebnis-Normalisierung: {str(e)}")
            return {
                'id': 'unknown',
                'title': 'Fehler bei der Datenverarbeitung',
                'organization': 'Unbekannt',
                'source_api': 'ted',
                'error': str(e)
            }

    def _extract_date(self, date_field: Any) -> Optional[str]:
        """
        Extrahiert und normalisiert Datumsfelder aus TED-API-Antworten
        
        Args:
            date_field: Datumsfeld aus der API-Antwort
            
        Returns:
            Normalisiertes Datum im ISO-Format oder None
        """
        if not date_field:
            return None
        
        if isinstance(date_field, list) and date_field:
            date_str = date_field[0]
        elif isinstance(date_field, str):
            date_str = date_field
        else:
            return None
        
        try:
            # TED verwendet oft das Format YYYY-MM-DD
            if len(date_str) >= 10:
                return date_str[:10]
            return None
        except:
            return None

    def _extract_value(self, value_field: Any, currency_field: Any) -> tuple:
        """
        Extrahiert Auftragswert und Währung aus TED-API-Antworten
        
        Args:
            value_field: Wert-Feld aus der API-Antwort
            currency_field: Währungs-Feld aus der API-Antwort
            
        Returns:
            Tuple (value, currency)
        """
        value = 0
        currency = 'EUR'  # Standard für EU-Ausschreibungen
        
        # Auftragswert extrahieren
        if value_field:
            if isinstance(value_field, list) and value_field:
                try:
                    value = float(value_field[0])
                except (ValueError, TypeError):
                    value = 0
            elif isinstance(value_field, (int, float)):
                value = float(value_field)
        
        # Währung extrahieren
        if currency_field:
            if isinstance(currency_field, list) and currency_field:
                currency = currency_field[0]
            elif isinstance(currency_field, str):
                currency = currency_field
        
        return value, currency

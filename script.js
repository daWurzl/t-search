/**
 * Hauptskript für die öffentliche Ausschreibungen Suchwebseite
 * Verwaltet die Benutzerinteraktion, API-Aufrufe und Datenvisualisierung
 */

class PublicTenderSearch {
    constructor() {
        // Grundlegende Initialisierung
        this.currentResults = [];
        this.filteredResults = [];
        this.currentPage = 1;
        this.itemsPerPage = 10;
        this.searchRunId = null;
        
        // GitHub Repository Konfiguration
        this.config = {
            owner: 'IHR_GITHUB_USERNAME', // Hier Ihren GitHub Username eintragen
            repo: 'public-tender-search',
            workflowFile: 'search.yml'
        };
        
        this.init();
    }

    /**
     * Initialisiert die Anwendung und bindet Event-Listener
     */
    init() {
        this.bindEvents();
        this.setDefaultDates();
        this.checkForPendingResults();
    }

    /**
     * Bindet alle Event-Listener an die entsprechenden DOM-Elemente
     */
    bindEvents() {
        // Suchformular
        document.getElementById('searchForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.startSearch();
        });

        // Export-Button
        document.getElementById('exportCsvBtn').addEventListener('click', () => {
            this.exportToCSV();
        });

        // Aktualisieren-Button
        document.getElementById('refreshBtn').addEventListener('click', () => {
            this.refreshResults();
        });

        // Filter und Sortierung
        document.getElementById('apiFilter').addEventListener('change', () => {
            this.applyFilters();
        });

        document.getElementById('sortBy').addEventListener('change', () => {
            this.applySorting();
        });
    }

    /**
     * Setzt Standard-Datumswerte (letzte 30 Tage)
     */
    setDefaultDates() {
        const today = new Date();
        const thirtyDaysAgo = new Date(today.getTime() - (30 * 24 * 60 * 60 * 1000));
        
        document.getElementById('dateTo').value = today.toISOString().split('T')[0];
        document.getElementById('dateFrom').value = thirtyDaysAgo.toISOString().split('T')[0];
    }

    /**
     * Startet eine neue Suche über GitHub Actions
     */
    async startSearch() {
        const formData = this.collectSearchParameters();
        
        if (!this.validateSearchParameters(formData)) {
            return;
        }

        try {
            this.showStatusSection();
            this.updateStatus('Suche wird gestartet...', 10);
            
            // GitHub Actions Workflow triggern
            const runId = await this.triggerGitHubWorkflow(formData);
            this.searchRunId = runId;
            
            this.updateStatus('Suche läuft... APIs werden abgefragt', 30);
            
            // Polling für Ergebnisse starten
            this.pollForResults(runId);
            
        } catch (error) {
            console.error('Fehler beim Starten der Suche:', error);
            this.showError('Fehler beim Starten der Suche: ' + error.message);
        }
    }

    /**
     * Sammelt alle Suchparameter aus dem Formular
     */
    collectSearchParameters() {
        const form = document.getElementById('searchForm');
        const formData = new FormData(form);
        
        // Ausgewählte APIs sammeln
        const selectedApis = [];
        formData.getAll('apis').forEach(api => selectedApis.push(api));
        
        return {
            searchTerm: formData.get('searchTerm'),
            apis: selectedApis,
            dateFrom: formData.get('dateFrom'),
            dateTo: formData.get('dateTo'),
            minValue: formData.get('minValue') || 0
        };
    }

    /**
     * Validiert die eingegebenen Suchparameter
     */
    validateSearchParameters(params) {
        if (!params.searchTerm || params.searchTerm.trim().length < 3) {
            this.showError('Bitte geben Sie einen Suchbegriff mit mindestens 3 Zeichen ein.');
            return false;
        }

        if (!params.apis || params.apis.length === 0) {
            this.showError('Bitte wählen Sie mindestens eine API aus.');
            return false;
        }

        if (params.dateFrom && params.dateTo) {
            const fromDate = new Date(params.dateFrom);
            const toDate = new Date(params.dateTo);
            
            if (fromDate > toDate) {
                this.showError('Das "Von"-Datum muss vor dem "Bis"-Datum liegen.');
                return false;
            }
        }

        return true;
    }

    /**
     * Triggert den GitHub Actions Workflow mit den Suchparametern
     */
    async triggerGitHubWorkflow(params) {
        const token = await this.getGitHubToken();
        
        const response = await fetch(`https://api.github.com/repos/${this.config.owner}/${this.config.repo}/actions/workflows/${this.config.workflowFile}/dispatches`, {
            method: 'POST',
            headers: {
                'Authorization': `token ${token}`,
                'Accept': 'application/vnd.github.v3+json',
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                ref: 'main',
                inputs: {
                    search_term: params.searchTerm,
                    apis: params.apis.join(','),
                    date_from: params.dateFrom,
                    date_to: params.dateTo,
                    min_value: params.minValue.toString()
                }
            })
        });

        if (!response.ok) {
            throw new Error(`GitHub API Fehler: ${response.status}`);
        }

        // Neueste Workflow-Run-ID abrufen
        return await this.getLatestWorkflowRunId();
    }

    /**
     * Ruft die neueste Workflow-Run-ID ab
     */
    async getLatestWorkflowRunId() {
        const token = await this.getGitHubToken();
        
        const response = await fetch(`https://api.github.com/repos/${this.config.owner}/${this.config.repo}/actions/runs?per_page=1`, {
            headers: {
                'Authorization': `token ${token}`,
                'Accept': 'application/vnd.github.v3+json'
            }
        });

        const data = await response.json();
        return data.workflow_runs[0]?.id;
    }

    /**
     * Pollt regelmäßig nach den Ergebnissen des Workflows
     */
    async pollForResults(runId) {
        const maxAttempts = 60; // 5 Minuten bei 5-Sekunden-Intervallen
        let attempts = 0;

        const pollInterval = setInterval(async () => {
            attempts++;
            
            try {
                const status = await this.checkWorkflowStatus(runId);
                
                if (status === 'completed') {
                    clearInterval(pollInterval);
                    this.updateStatus('Ergebnisse werden geladen...', 90);
                    await this.loadResults(runId);
                    this.updateStatus('Suche abgeschlossen!', 100);
                    setTimeout(() => this.hideStatusSection(), 2000);
                    
                } else if (status === 'failed') {
                    clearInterval(pollInterval);
                    this.showError('Die Suche ist fehlgeschlagen. Bitte versuchen Sie es erneut.');
                    
                } else {
                    // Fortschritt aktualisieren
                    const progress = Math.min(30 + (attempts * 2), 80);
                    this.updateStatus(`Suche läuft... (${attempts}/${maxAttempts})`, progress);
                }

                if (attempts >= maxAttempts) {
                    clearInterval(pollInterval);
                    this.showError('Timeout: Die Suche dauert zu lange. Bitte versuchen Sie es später erneut.');
                }
                
            } catch (error) {
                console.error('Fehler beim Überprüfen des Workflow-Status:', error);
            }
        }, 5000); // Alle 5 Sekunden prüfen
    }

    /**
     * Überprüft den Status eines GitHub Actions Workflows
     */
    async checkWorkflowStatus(runId) {
        const token = await this.getGitHubToken();
        
        const response = await fetch(`https://api.github.com/repos/${this.config.owner}/${this.config.repo}/actions/runs/${runId}`, {
            headers: {
                'Authorization': `token ${token}`,
                'Accept': 'application/vnd.github.v3+json'
            }
        });

        const data = await response.json();
        return data.conclusion || data.status;
    }

    /**
     * Lädt die Ergebnisse nach Abschluss des Workflows
     */
    async loadResults(runId) {
        try {
            // Artefakte vom Workflow herunterladen
            const artifacts = await this.getWorkflowArtifacts(runId);
            const resultsArtifact = artifacts.find(a => a.name === 'search-results');
            
            if (!resultsArtifact) {
                throw new Error('Keine Ergebnisse gefunden');
            }

            // Ergebnisse herunterladen und verarbeiten
            const results = await this.downloadAndParseResults(resultsArtifact.archive_download_url);
            
            this.currentResults = results;
            this.filteredResults = [...results];
            
            this.displayResults();
            this.displayStatistics();
            this.showResultsSection();
            
        } catch (error) {
            console.error('Fehler beim Laden der Ergebnisse:', error);
            this.showError('Fehler beim Laden der Ergebnisse: ' + error.message);
        }
    }

    /**
     * Ruft die Artefakte eines Workflow-Runs ab
     */
    async getWorkflowArtifacts(runId) {
        const token = await this.getGitHubToken();
        
        const response = await fetch(`https://api.github.com/repos/${this.config.owner}/${this.config.repo}/actions/runs/${runId}/artifacts`, {
            headers: {
                'Authorization': `token ${token}`,
                'Accept': 'application/vnd.github.v3+json'
            }
        });

        const data = await response.json();
        return data.artifacts;
    }

    /**
     * Lädt und parst die Ergebnisse aus einem Artefakt
     */
    async downloadAndParseResults(downloadUrl) {
        // In einer echten Implementierung würde hier das ZIP-Artefakt 
        // heruntergeladen und die JSON-Datei extrahiert werden
        // Für diese Demo simulieren wir Beispieldaten
        
        return this.generateSampleResults();
    }

    /**
     * Generiert Beispieldaten für die Demo
     */
    generateSampleResults() {
        const sampleResults = [];
        const apis = ['ted', 'openopps', 'sam', 'contracts_finder'];
        const titles = [
            'IT-Dienstleistungen für Verwaltung',
            'Bauarbeiten Straßenerneuerung',
            'Consulting Services für Digitalisierung',
            'Medizinische Ausrüstung',
            'Facility Management Services',
            'Software-Entwicklung',
            'Reinigungsdienstleistungen',
            'Sicherheitsdienstleistungen',
            'Catering Services',
            'Transportdienstleistungen'
        ];
        
        const organizations = [
            'Bundesministerium für Verkehr',
            'Stadt München',
            'NHS Trust London',
            'US Department of Defense',
            'Région Île-de-France',
            'City of Amsterdam',
            'Governo Italiano',
            'Swedish Transport Administration'
        ];

        const countries = ['DE', 'UK', 'US', 'FR', 'IT', 'NL', 'SE'];

        for (let i = 0; i < 50; i++) {
            const api = apis[Math.floor(Math.random() * apis.length)];
            const publishDate = new Date(Date.now() - Math.random() * 30 * 24 * 60 * 60 * 1000);
            const deadline = new Date(publishDate.getTime() + Math.random() * 60 * 24 * 60 * 60 * 1000);
            
            sampleResults.push({
                id: `${api}-${i}`,
                api: api,
                title: titles[Math.floor(Math.random() * titles.length)],
                organization: organizations[Math.floor(Math.random() * organizations.length)],
                value: Math.floor(Math.random() * 1000000) + 10000,
                currency: 'EUR',
                publishDate: publishDate.toISOString().split('T')[0],
                deadline: deadline.toISOString().split('T')[0],
                country: countries[Math.floor(Math.random() * countries.length)],
                url: `https://example.com/tender/${api}-${i}`,
                description: `Ausschreibung für ${titles[Math.floor(Math.random() * titles.length)]}`
            });
        }

        return sampleResults;
    }

    /**
     * Zeigt die Ergebnisse in der Tabelle an
     */
    displayResults() {
        const tbody = document.getElementById('resultsTableBody');
        tbody.innerHTML = '';

        // Pagination berechnen
        const startIndex = (this.currentPage - 1) * this.itemsPerPage;
        const endIndex = startIndex + this.itemsPerPage;
        const pageResults = this.filteredResults.slice(startIndex, endIndex);

        pageResults.forEach(result => {
            const row = this.createResultRow(result);
            tbody.appendChild(row);
        });

        this.updatePagination();
    }

    /**
     * Erstellt eine Tabellenzeile für ein Suchergebnis
     */
    createResultRow(result) {
        const row = document.createElement('tr');
        
        row.innerHTML = `
            <td>
                <span class="api-badge ${result.api}">${this.getApiDisplayName(result.api)}</span>
            </td>
            <td>
                <strong>${this.escapeHtml(result.title)}</strong>
                <br>
                <small class="text-muted">${this.escapeHtml(result.description?.substring(0, 100) || '')}...</small>
            </td>
            <td>${this.escapeHtml(result.organization)}</td>
            <td>
                <span class="value-amount">${this.formatCurrency(result.value, result.currency)}</span>
            </td>
            <td>${this.formatDate(result.publishDate)}</td>
            <td>${this.formatDate(result.deadline)}</td>
            <td>
                <img src="https://flagcdn.com/16x12/${result.country.toLowerCase()}.png" 
                     alt="${result.country}" width="16" height="12">
                ${result.country}
            </td>
            <td>
                <a href="${result.url}" target="_blank" class="action-btn view-btn">
                    <i class="fas fa-external-link-alt"></i> Anzeigen
                </a>
            </td>
        `;

        return row;
    }

    /**
     * Zeigt Statistiken über die Suchergebnisse an
     */
    displayStatistics() {
        const stats = this.calculateStatistics();
        const statsGrid = document.getElementById('statsGrid');
        
        statsGrid.innerHTML = `
            <div class="stat-card">
                <span class="stat-number">${stats.total}</span>
                <span class="stat-label">Gesamte Ergebnisse</span>
            </div>
            <div class="stat-card">
                <span class="stat-number">${stats.totalValue}</span>
                <span class="stat-label">Gesamtwert (EUR)</span>
            </div>
            <div class="stat-card">
                <span class="stat-number">${stats.averageValue}</span>
                <span class="stat-label">Durchschnittswert (EUR)</span>
            </div>
            <div class="stat-card">
                <span class="stat-number">${stats.countries}</span>
                <span class="stat-label">Länder</span>
            </div>
        `;
    }

    /**
     * Berechnet Statistiken für die aktuellen Ergebnisse
     */
    calculateStatistics() {
        const total = this.currentResults.length;
        const totalValue = this.currentResults.reduce((sum, r) => sum + r.value, 0);
        const averageValue = total > 0 ? Math.round(totalValue / total) : 0;
        const countries = new Set(this.currentResults.map(r => r.country)).size;

        return {
            total: total.toLocaleString(),
            totalValue: this.formatCurrency(totalValue, 'EUR'),
            averageValue: this.formatCurrency(averageValue, 'EUR'),
            countries
        };
    }

    /**
     * Wendet Filter auf die Ergebnisse an
     */
    applyFilters() {
        const apiFilter = document.getElementById('apiFilter').value;
        
        this.filteredResults = this.currentResults.filter(result => {
            if (apiFilter && result.api !== apiFilter) {
                return false;
            }
            return true;
        });

        this.currentPage = 1;
        this.displayResults();
    }

    /**
     * Wendet Sortierung auf die Ergebnisse an
     */
    applySorting() {
        const sortBy = document.getElementById('sortBy').value;
        
        this.filteredResults.sort((a, b) => {
            switch (sortBy) {
                case 'date':
                    return new Date(b.publishDate) - new Date(a.publishDate);
                case 'value':
                    return b.value - a.value;
                case 'title':
                    return a.title.localeCompare(b.title);
                case 'deadline':
                    return new Date(a.deadline) - new Date(b.deadline);
                default:
                    return 0;
            }
        });

        this.displayResults();
    }

    /**
     * Aktualisiert die Pagination
     */
    updatePagination() {
        const totalPages = Math.ceil(this.filteredResults.length / this.itemsPerPage);
        const pagination = document.getElementById('pagination');
        
        if (totalPages <= 1) {
            pagination.style.display = 'none';
            return;
        }

        pagination.style.display = 'flex';
        pagination.innerHTML = '';

        // Zurück-Button
        const prevBtn = document.createElement('button');
        prevBtn.textContent = '‹ Zurück';
        prevBtn.disabled = this.currentPage === 1;
        prevBtn.onclick = () => {
            if (this.currentPage > 1) {
                this.currentPage--;
                this.displayResults();
            }
        };
        pagination.appendChild(prevBtn);

        // Seitenzahlen
        const startPage = Math.max(1, this.currentPage - 2);
        const endPage = Math.min(totalPages, this.currentPage + 2);

        for (let i = startPage; i <= endPage; i++) {
            const pageBtn = document.createElement('button');
            pageBtn.textContent = i;
            pageBtn.className = i === this.currentPage ? 'active' : '';
            pageBtn.onclick = () => {
                this.currentPage = i;
                this.displayResults();
            };
            pagination.appendChild(pageBtn);
        }

        // Weiter-Button
        const nextBtn = document.createElement('button');
        nextBtn.textContent = 'Weiter ›';
        nextBtn.disabled = this.currentPage === totalPages;
        nextBtn.onclick = () => {
            if (this.currentPage < totalPages) {
                this.currentPage++;
                this.displayResults();
            }
        };
        pagination.appendChild(nextBtn);
    }

    /**
     * Exportiert die aktuellen Ergebnisse als CSV-Datei
     */
    exportToCSV() {
        if (this.filteredResults.length === 0) {
            this.showError('Keine Ergebnisse zum Exportieren vorhanden.');
            return;
        }

        const headers = [
            'API', 'Titel', 'Organisation', 'Auftragswert', 'Währung', 
            'Veröffentlichung', 'Einreichungsfrist', 'Land', 'URL', 'Beschreibung'
        ];

        const csvContent = [
            headers.join(','),
            ...this.filteredResults.map(result => [
                `"${result.api}"`,
                `"${this.escapeCSV(result.title)}"`,
                `"${this.escapeCSV(result.organization)}"`,
                result.value,
                `"${result.currency}"`,
                `"${result.publishDate}"`,
                `"${result.deadline}"`,
                `"${result.country}"`,
                `"${result.url}"`,
                `"${this.escapeCSV(result.description || '')}"`
            ].join(','))
        ].join('\n');

        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        
        if (link.download !== undefined) {
            const url = URL.createObjectURL(blob);
            link.setAttribute('href', url);
            link.setAttribute('download', `ausschreibungen_${new Date().toISOString().split('T')[0]}.csv`);
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }
    }

    /**
     * Hilfsfunktionen für die Datenformatierung
     */
    getApiDisplayName(api) {
        const names = {
            'ted': 'TED',
            'openopps': 'OpenOpps',
            'sam': 'SAM.gov',
            'contracts_finder': 'CF'
        };
        return names[api] || api.toUpperCase();
    }

    formatCurrency(amount, currency) {
        return new Intl.NumberFormat('de-DE', {
            style: 'currency',
            currency: currency || 'EUR'
        }).format(amount);
    }

    formatDate(dateString) {
        return new Date(dateString).toLocaleDateString('de-DE');
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    escapeCSV(text) {
        return text.replace(/"/g, '""');
    }

    /**
     * UI-Management Funktionen
     */
    showStatusSection() {
        document.getElementById('statusSection').style.display = 'block';
        document.getElementById('resultsSection').style.display = 'none';
    }

    hideStatusSection() {
        document.getElementById('statusSection').style.display = 'none';
    }

    showResultsSection() {
        document.getElementById('resultsSection').style.display = 'block';
    }

    updateStatus(message, progress) {
        document.getElementById('statusMessage').innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${message}`;
        document.querySelector('.progress-fill').style.width = `${progress}%`;
    }

    showError(message) {
        this.hideStatusSection();
        
        // Bestehende Fehlermeldungen entfernen
        const existingErrors = document.querySelectorAll('.message.error');
        existingErrors.forEach(error => error.remove());
        
        // Neue Fehlermeldung erstellen
        const errorDiv = document.createElement('div');
        errorDiv.className = 'message error';
        errorDiv.innerHTML = `<i class="fas fa-exclamation-triangle"></i> ${message}`;
        
        // Nach dem Suchformular einfügen
        const searchSection = document.querySelector('.search-section');
        searchSection.appendChild(errorDiv);
        
        // Nach 5 Sekunden automatisch entfernen
        setTimeout(() => {
            if (errorDiv.parentNode) {
                errorDiv.remove();
            }
        }, 5000);
    }

    /**
     * GitHub Token Management (vereinfacht für Demo)
     */
    async getGitHubToken() {
        // In einer echten Anwendung sollte das Token sicher verwaltet werden
        // Für diese Demo nehmen wir an, dass es als Umgebungsvariable verfügbar ist
        return 'ghp_IHRGITHUBTOKEN'; // Hier Ihr GitHub Personal Access Token eintragen
    }

    /**
     * Prüft nach ausstehenden Ergebnissen beim Laden der Seite
     */
    checkForPendingResults() {
        const urlParams = new URLSearchParams(window.location.search);
        const runId = urlParams.get('run_id');
        
        if (runId) {
            this.searchRunId = runId;
            this.showStatusSection();
            this.updateStatus('Prüfe ausstehende Suche...', 50);
            this.pollForResults(runId);
        }
    }

    /**
     * Aktualisiert die Ergebnisse manuell
     */
    async refreshResults() {
        if (this.searchRunId) {
            this.showStatusSection();
            this.updateStatus('Ergebnisse werden aktualisiert...', 50);
            await this.loadResults(this.searchRunId);
            this.hideStatusSection();
        }
    }
}

// Anwendung initialisieren, wenn das DOM geladen ist
document.addEventListener('DOMContentLoaded', () => {
    new PublicTenderSearch();
});

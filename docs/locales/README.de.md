# Crypto AI Trading Lab

[简体中文](https://github.com/chenbinghan666/crypto-ai-trading-lab/blob/main/README.md) · [English](https://github.com/chenbinghan666/crypto-ai-trading-lab/blob/main/docs/locales/README.en.md) · [日本語](https://github.com/chenbinghan666/crypto-ai-trading-lab/blob/main/docs/locales/README.ja.md) · **Deutsch** · [Français](https://github.com/chenbinghan666/crypto-ai-trading-lab/blob/main/docs/locales/README.fr.md) · [Español](https://github.com/chenbinghan666/crypto-ai-trading-lab/blob/main/docs/locales/README.es.md) · [Português](https://github.com/chenbinghan666/crypto-ai-trading-lab/blob/main/docs/locales/README.pt.md)

Chinesischsprachige Arbeitsumgebung für Backtests, FreqAI-Experimente und simulierten Futures-Handel. Regelbasierte und modellbasierte Strategien lassen sich über getrennte virtuelle Konten vergleichen. Der Einsatz ist auf Forschung und Simulation ausgelegt.

Python · Freqtrade · FreqAI

Ein unabhängiges Kryptowährungs-Recherche- und Vertragssimulationssystem, das chinesische Webverwaltungsseiten bereitstellt und Freqtrade/FreqUI, FreqAI CPU LightGBM und TradingAgents/DeepSeek integriert. Die Laufzeit ist nicht auf Codex oder Chat-Sitzungen angewiesen.

**unterstützt derzeit nur Forschung und virtuellen Handel, realer Handel ist verboten. Weder Strategien noch Modelle stellen eine nachgewiesene Rentabilität dar.**

## Funktion

- Öffentliche Binance-Kurse, Verbindungsdiagnose, K-Line und Aktualisierungs-Countdown; Die permanenten öffentlichen Kurse von Gate werden zur unabhängigen Vertragssimulation verwendet.
- Auf Binance U basierende Vertragskonten sind schreibgeschützt, um Vermögenswerte und Positionen abzufragen. API-Konfigurationen werden verschlüsselt und lokal gespeichert.
- TradingAgents / DeepSeek-Rechercheaufgaben, API-Nutzungsabrechnung, Budgetreservierungen und Gebührenlimits.
- FreqAI-CPU-Training, zeitisolierte Auswertung, Modellspeicherung und Neuladevalidierung.
- Offizielles Freqtrade-Kontrakt-Backtesting und Echtzeit-Probelauf: Long- und Short-Positionen, Eröffnungs- und Schlussaufträge, Transaktionsstatus sowie Gewinn und Verlust.
- Automatische Optimierung: Generieren Sie Kandidaten, trainieren und kalkulieren Sie Out-of-Sample-Vergleiche, wechseln Sie Simulationsversionen durch Post-Short-Positionen und führen Sie einen Rollback durch, wenn sich die Leistung verschlechtert.
- 15-minütiges KI-Kontrollexperiment: Die Regelgruppe und die FreqAI-Modellgruppe verwenden unabhängige virtuelle Hauptbücher, um Signale, Transaktionsaufzeichnungen sowie Gewinne und Verluste zu vergleichen.
- Unabhängiger Prozessdämon, Verbindungswiederherstellung, Zustandswiederherstellung, Auftragsdeduplizierung, Windows-Start und -Stopp mit einem Klick und Docker Compose-Konfiguration.

## Windows startet

Informationen zur Umgebungsvorbereitung und Abhängigkeitsinstallation finden Sie unter [Windows-Installation](../../docs/INSTALL_WINDOWS.md) und [Bereitstellungsanweisungen](../../docs/DEPLOYMENT.md). Erfordert WSL/Ubuntu und eine kompatible Python-Umgebung; Windows-Skripte erkennen den Projektpfad.

1. Klonen Sie das Repository und bereiten Sie WSL und Abhängigkeiten gemäß der Installationsdokumentation vor.
2. Doppelklicken Sie auf `启动系统.cmd`, um auf <http://127.0.0.1:8080> zuzugreifen.
3. Doppelklicken Sie auf `FreqUI登录信息.cmd`, um das lokale Verwaltungskennwort anzuzeigen und das Bedienfeld auf der Webseite zu entsperren.
4. Konfigurieren Sie die erforderlichen APIs im Web, überprüfen Sie Preise und Dienste und aktivieren Sie manuell Recherche, Schulung oder Simulation.
5. Doppelklicken Sie auf `停止系统.cmd`, um den Dienst zu stoppen, und auf `查看状态.cmd`, um den Ausführungsstatus anzuzeigen.

Das Schließen des Browsers oder der Entwicklungstools hat keine Auswirkungen auf Hintergrunddienste; Durch das Herunterfahren oder den Ruhezustand des Computers werden lokale Vorgänge unterbrochen. Bei neuen Bereitstellungen werden Simulation und automatische Optimierung nicht standardmäßig gestartet. Das Warehouse enthält nicht die Konfiguration, Schlüssel, Modelle und laufenden Daten des Entwicklers und muss nach dem Klonen selbst initialisiert werden.

Offizielle Forschungsfrequenz: <http://127.0.0.1:8081>. Schreibgeschützte FreqUI nach dem ursprünglichen 1-Stunden-Simulationsstart: <http://127.0.0.1:8083>.

## Docker Compose

```sh
docker compose up -d --build
docker compose down
```

Der Standardport ist nur an den lokalen Computer gebunden. Für die erste Bereitstellung müssen Sie die Anmeldeinformationen und Modulschalter selbst konfigurieren. Die wichtigsten Bildkonfigurationen für das Programm und den Forschungsdienst wurden bereitgestellt. Der eigentliche Docker-Build und die Linux-VPS-Bereitstellung müssen noch in der Zielumgebung akzeptiert werden.

## Die Grenze zwischen Simulation und KI

Simulieren Sie die Verwendung virtueller Gelder ohne Börsenhandelserlaubnis. Der aktuelle Hebel ist auf 1x festgelegt und die Grenzwerte für unabhängige Positionen, Tagesverluste, Drawdowns und aufeinanderfolgende Verlustkühlungen werden beibehalten. Die Strategie wird anhand der abschließenden K-Linie bewertet. Nullhandel ist zulässig, wenn kein Signal vorliegt oder die Risikokontrolle nicht freigegeben wurde.

Die KI im kontrollierten 15-m-Experiment bezieht sich auf die lokale FreqAI LightGBM-Vorhersagefilterung. TradingAgents / DeepSeek ist ein separater Recherche- und Optimierungsprozess. Das experimentelle Modell wurde nicht gewinnbringend akzeptiert und die experimentellen Ergebnisse werden die ursprüngliche Kontostrategie nicht direkt ersetzen. Die automatische Optimierung passt nur eingeschränkte Parameter und Modelle an und führt keinen beliebigen, von der KI generierten Code aus.

Informationen zu Bearbeitungsgebühren, Slippage-Gebührenumrechnung, Kapitalgebühren, Schulungsdatenisolierung und Endkontrollregeln finden Sie in den entsprechenden Dokumenten. Die Kostenumrechnung kann die tatsächlichen Auswirkungen der Transaktion nicht vollständig abbilden und kurzfristige simulierte Renditen können die Wirksamkeit der Strategie nicht beweisen.

## Anmeldeinformationen und Betriebsdaten

Geben Sie den API-Schlüssel nur auf der lokalen Webseite ein, übermitteln Sie ihn nicht an GitHub, Issue oder Chat. Verwenden Sie schreibgeschützte Binance-Kontoberechtigungen; Transaktionen werden mit diesem Konto nicht ausgeführt. DeepSeek-Anrufe unterliegen der Gültigkeit der Budget- und Preisüberprüfung.

Native Umgebungsdateien, Schlüssel, Datenbanken, Modelle, Protokolle, Laufberichte und Screenshots werden von `.gitignore` ausgeschlossen. Das öffentliche Repository enthält nur Quellcode, Konfigurationsvorlagen, Tests und Dokumentation. Nach der Ausführung des Programms generierte Berichte verbleiben auf dem lokalen Computer.

## Dokumentation

- [Bereitstellung und Fehlerbehebung](../../docs/DEPLOYMENT.md) · [Wiederherstellungshandbuch](../../docs/RECOVERY.md)
- [Webseitenbetrieb](../../docs/WEB_CONTROLS.md) · [Konto schreibgeschützte Bindung](../../docs/BINANCE_ACCOUNT.md)
- [Vertragssimulation](../../docs/PAPER_TRADING.md) · [15m KI-Kontrollexperiment](../../docs/FAST_AI_EXPERIMENT.md)
- [FreqAI CPU](../../docs/FREQAI_CPU.md) · [AI Research](../../docs/AI_RESEARCH.md)
- [optimiert automatisch die Risikorichtlinie](../../docs/AUTOMATIC_OPTIMIZATION.md) · [](../../docs/RISK_POLICY.md)
- [unabhängige Betriebsabnahme](../../docs/INDEPENDENCE_ACCEPTANCE.md)

## Entwicklungsüberprüfung

```powershell
.\scripts\lab.ps1 test
```

Sie müssen zuerst die im Dokument angegebenen laufenden Abhängigkeiten installieren. Die Skripte für Netzwerkakzeptanz, unabhängige Hintergrundwiederherstellung und experimentelle Serviceakzeptanz befinden sich unter `scripts/`; Einige Skripte erfordern, dass lokale Dienste gestartet wurden. Die Annahmeausgabe wird nicht mit dem Lager freigegeben.

Zu den vom Projekt verwendeten Upstreams gehören [Freqtrade](https://github.com/freqtrade/freqtrade) und [TradingAgents](https://github.com/TauricResearch/TradingAgents). Abhängigkeitsversionen sind in der Anforderungssperrdatei festgelegt und die Upstream-Software folgt ihren jeweiligen Lizenzen.

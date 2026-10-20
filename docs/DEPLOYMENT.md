# Vercel und lokale Handelsengine

Vercel-Projekt: https://vercel.com/studentley/hedgefund
Produktionsadresse: https://hedgefund-dusky.vercel.app/
Git-Quelle: deumont/HedgeFund, Branch main. Root Directory: frontend.
Vite baut über npm run build nach dist; frontend/vercel.json speichert dies.

Die Handelsengine, ihre SQLite-Datenbank, Zugangsdaten und der dauerhafte Worker
laufen weiterhin auf dem Windows-PC. Vercel hostet das Frontend. Eine statische
Veröffentlichung stellt keine Python-API, Datenbank oder laufenden Trader bereit.
Insbesondere darf kein lokales .env in den Frontend-Build geladen werden.

Bei fehlender API zeigt die Website einen erklärten Verbindungszustand und
einen Link zur geschützten lokalen Konsole http://127.0.0.1:8765/.
Passworteingabe wird erst angeboten, wenn die API tatsächlich antwortet.
Start.cmd startet den lokalen Betrieb; das Passwort steht in local-access.txt.
Anmeldung und sämtliche Datenansichten sind auf dem PC lokal erreichbar.
Der Link funktioniert nur auf dem Rechner, auf dem die Engine läuft.

Für Anmeldung von anderen Geräten fehlt weiterhin ein geschützter, dauerhaft
erreichbarer Backend-Host oder HTTPS/VPN-Zugang zum PC. Kein öffentlicher Tunnel,
kein Serverless-SQLite-Ersatz und keine Attrappe mit erfundenen Kontodaten wurde
eingerichtet. Der lokale Handelsbetrieb benötigt Vercel nicht.

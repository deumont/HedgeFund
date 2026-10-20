# Vercel und lokale Handelsengine

Vercel-Projekt: https://vercel.com/studentley/hedgefund
Produktionsadresse: https://hedgefund-dusky.vercel.app/
Git-Quelle: deumont/HedgeFund, Branch main. Root Directory: frontend.
Vite baut über npm run build nach dist; frontend/vercel.json speichert dies.

Die Handelsengine, ihre SQLite-Datenbank, Zugangsdaten und der dauerhafte Worker
laufen weiterhin auf dem Windows-PC. Vercel hostet das Frontend. Eine statische
Veröffentlichung stellt keine Python-API, Datenbank oder laufenden Trader bereit.
Insbesondere darf kein lokales .env in den Frontend-Build geladen werden.

Mit den öffentlichen VITE_SUPABASE_URL/VITE_SUPABASE_PUBLISHABLE_KEY Variablen
verwendet Vercel Supabase Auth und private Cloud-Snapshots. Nur freigeschaltete
atlas_members dürfen die Konsole lesen und Aktionen vormerken. Das persönliche
CEO-Konto muss noch vom Benutzer angelegt und freigeschaltet werden.
Start.cmd startet den lokalen Betrieb; dessen eigenes Passwort steht weiterhin
in local-access.txt. Servergeheimnisse stehen niemals in Vercel-VITE-Variablen.

Cloud-Zugriff und Ausführung: siehe CLOUD.md. Supabase hält private Snapshots
auch bei ausgeschaltetem PC vor; neue Orders benötigen die lokale Engine.
Kein öffentlicher Tunnel und kein zweiter SQLite-/Trading-Worker eingerichtet.

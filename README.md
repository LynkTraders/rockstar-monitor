# Rockstar Monitor

WhatsApp-alert zodra Rockstar zelf iets naar buiten brengt. Geen gamingpers,
geen geruchten, geen ruis — alleen officiële bronnen.

## Bronnen

| Bron | Wat het oplevert | Status |
|---|---|---|
| **Rockstar Newswire** | Alle officiële aankondigingen, met tag per game | Werkt (GraphQL, geen key nodig) |
| **Rockstar YouTube** | Trailers en video's | Werkt (RSS) |
| **Take-Two IR** | Persberichten: releasedata, uitstel, pre-orders | Werkt (RSS, gefilterd op Rockstar) |
| **X / @RockstarGames** | Alleen een seintje *dát* er gepost is | Zie hieronder |

### Waarom X maar half meedoet

De inhoud van tweets is sinds de API-wijzigingen niet meer gratis op te halen.
Nitter is dood, de publieke RSS-bruggen zijn dood, en de embed-endpoint van X
geeft direct `429 Rate limit exceeded`. De officiële X API kost $200/maand voor
het laagste betaalde niveau.

Wat wél gratis werkt is de tweetteller van het profiel. Loopt die op, dan krijg
je een appje "Rockstar heeft X keer gepost" met een link naar het account. Je
weet dus *dat* er iets is, niet *wat*.

In de praktijk maakt dat weinig uit: Rockstar tweet vrijwel altijd een link
naar de Newswire, en die haalt deze monitor al binnen — meestal eerder dan de
tweet zelf. Wil je X helemaal niet, zet dan `WATCH_X` op `false`.

## Instellen

### 1. Secrets

**Settings → Secrets and variables → Actions → Secrets:**

| Secret | Waarde |
|---|---|
| `WHATSAPP_PHONE` | Telefoonnummer zonder `+`, bijv. `31612345678` |
| `WHATSAPP_APIKEY` | CallMeBot API-key |

Geen key? Stuur `I allow callmebot to send me messages` via WhatsApp naar
**+34 623 78 64 49**; je krijgt de key terug.

### 2. Variables (optioneel)

**Settings → Secrets and variables → Actions → Variables:**

| Variable | Standaard | Betekenis |
|---|---|---|
| `ONLY_GTA6` | `false` | `true` = uitsluitend GTA VI-berichten |
| `WATCH_X` | `true` | `false` = X-teller negeren |

Op `false` krijg je alles van Rockstar: ongeveer twee tot drie berichten per
week, waarvan GTA VI-berichten bovenaan staan en als zodanig gemarkeerd zijn.
Op `true` blijft daar ongeveer één bericht per twee weken van over.

### 3. Starten

**Actions → Rockstar Monitor → Run workflow.** Vink eventueel *dry run* aan om
te kijken wat hij zou versturen zonder dat er iets verstuurd wordt.

Daarna draait hij vanzelf elke 5 minuten. GitHub voert `schedule`-workflows
niet op de seconde uit; reken op 5 tot 20 minuten vertraging bij drukte.

## Ruisbeheersing

- **Eerste run stuurt niets.** Alles wat er al staat wordt als gezien
  weggeschreven, zodat je niet overspoeld wordt bij het opstarten.
- **Dedup op titel.** Eén trailer staat in de Newswire én zes keer op YouTube
  (regiovarianten). Dat wordt één appje.
- **Take-Two wordt gefilterd.** NBA 2K, Zynga en WWE gaan eruit; alleen
  Rockstar, Grand Theft Auto en Red Dead blijven over.
- **Maximaal 8 appjes per run**, als noodrem.

## Lokaal testen

```bash
pip install -r requirements.txt
DRY_RUN=true python rockstar_monitor.py
```

`DRY_RUN=true` detecteert en logt alles, maar verstuurt niets. Wil je opnieuw
vanaf nul beginnen: verwijder `monitor_state.json`.

## Bestanden

| Bestand | Rol |
|---|---|
| `rockstar_monitor.py` | Het script |
| `.github/workflows/monitor.yml` | De planning |
| `monitor_state.json` | Wat al gezien is — wordt automatisch bijgewerkt |
| `requirements.txt` | `feedparser`, `requests` |

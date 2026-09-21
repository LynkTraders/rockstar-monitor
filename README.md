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

## Waar hij draait

Op twee plekken, met een gedeelde state:

| | Frequentie | Rol |
|---|---|---|
| **Mac** (launchd) | elke minuut | De echte monitor |
| **GitHub Actions** | elke 6 uur | Vangnet voor als de Mac uit staat |

Ze delen `monitor_state.json` via de repo: de Mac pullt voor elke run en pusht
alleen als er iets veranderd is. Wie een bericht als eerste ziet, meldt het;
de ander ziet dan dat het al gemeld is. Geen dubbele appjes.

### Waarom GitHub niet de hoofdroute is

De cron stond eerst op `*/5`. Gemeten over 62 uur leverde dat **21 runs op in
plaats van 743** — 3% van wat er gevraagd werd, met gaten tot 5,5 uur. GitHub
knijpt geplande workflows op gratis accounts af en geeft hoogfrequente schema's
de laagste prioriteit. De runs blijven groen, dus je ziet het niet. Vandaar de
Mac voor snelheid en GitHub voor dekking.

### Installatie op de Mac

```bash
git clone https://github.com/LynkTraders/rockstar-monitor.git ~/Developer/rockstar-monitor
cd ~/Developer/rockstar-monitor
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

mkdir -p ~/.config/rockstar-monitor
cat > ~/.config/rockstar-monitor/env <<'EOF'
WHATSAPP_PHONE=316xxxxxxxx
WHATSAPP_APIKEY=xxxxxxx
EOF
chmod 600 ~/.config/rockstar-monitor/env

sed "s|REPLACE_HOME|$HOME|g" mac/com.dennisweber.rockstar-monitor.plist \
  > ~/Library/LaunchAgents/com.dennisweber.rockstar-monitor.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.dennisweber.rockstar-monitor.plist
```

De credentials staan met opzet **buiten de repo** — die is publiek.

Log: `~/Library/Logs/rockstar-monitor.log`. Stoppen:
`launchctl bootout gui/$(id -u)/com.dennisweber.rockstar-monitor`.

### Bronnen niet elke minuut lastigvallen

Alle vier de bronnen elke minuut bevragen is 5.760 verzoeken per dag. Take-Two
publiceert hooguit wekelijks en fxtwitter is een kleine vrijwilligersdienst.
Daarom verdeelt de Mac ze (`SLOW_EVERY=5`, `X_EVERY=3`):

| Bron | Frequentie | Per dag |
|---|---|---|
| Newswire | elke run | 1.440 |
| X-teller | elke 3e run | 480 |
| YouTube | elke 5e run | 288 |
| Take-Two IR | elke 5e run | 288 |

Op GitHub staan beide op `1` — dat draait maar een paar keer per dag.

## Ruisbeheersing

- **Eerste run stuurt niets.** Alles wat er al staat wordt als gezien
  weggeschreven, zodat je niet overspoeld wordt bij het opstarten.
- **Dedup op titel.** Eén trailer staat in de Newswire én zes keer op YouTube
  (regiovarianten). Dat wordt één appje.
- **Take-Two wordt gefilterd.** NBA 2K, Zynga en WWE gaan eruit; alleen
  Rockstar, Grand Theft Auto en Red Dead blijven over.
- **Maximaal 8 appjes per run**, als noodrem.
- **Een mislukt appje telt niet als verstuurd.** Kan CallMeBot niet bereikt
  worden, dan draait het item zijn eigen state-wijziging terug en probeert de
  volgende run het opnieuw. Zonder dat zou een item als gemeld blijven staan
  terwijl het appje nooit aankwam — en dan hoor je er nooit meer iets over.

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
| `monitor_state.json` | Wat al gezien is — gedeeld tussen Mac en GitHub |
| `mac/run.sh` | Wrapper die de Mac elke minuut draait |
| `mac/*.plist` | launchd-sjabloon |
| `requirements.txt` | `feedparser`, `requests` |

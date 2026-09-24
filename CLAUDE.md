# Rockstar Monitor — context voor Claude

WhatsApp-alerts (via CallMeBot) zodra Rockstar iets officieels publiceert.
Gebouwd voor Dennis, september 2026.

## Waarom dit bestaat

De voorganger scande RSS-feeds van gamingpers — IGN, Kotaku, Gamespot, Polygon,
Eurogamer, VGC — op trefwoorden als "gta 6", "lucia" en "jason". Dat leverde een
stroom geruchten en herkauwd nieuws op, waarop Dennis de boel heeft uitgezet.
Daardoor miste hij bijna de pre-order van *GTA VI: The Album*.

De eis is daarom scherp: **alleen bronnen van Rockstar en Take-Two zelf**. Als
iets echt is, komt het van hen. Liever een bericht te laat dan tien te veel.

> Voeg geen gamingpers, aggregators, Reddit of nieuws-API's toe. Dat is precies
> het probleem dat deze versie oplost. Vraag het eerst aan Dennis.

## Architectuur

Twee runners, één gedeelde state:

| Runner | Frequentie | Rol |
|---|---|---|
| Mac (launchd) | elke minuut | De echte monitor |
| GitHub Actions | elke 6 uur | Vangnet voor als de Mac slaapt |

Ze delen `monitor_state.json` via deze repo. `mac/run.sh` pullt voor elke run en
pusht alleen als er echt iets veranderd is. Wie een bericht als eerste ziet,
meldt het; de ander ziet dan dat het al gemeld is. Geen dubbele appjes.

### Bronnen

| Bron | Hoe | Opmerking |
|---|---|---|
| Rockstar Newswire | GraphQL persisted query op `graph.rockstargames.com` | Geen key nodig. Levert tags per game, waarop GTA VI herkend wordt. |
| Rockstar YouTube | RSS, channel `UC6VcWc1rAoWdBCM0JxrRQ3A` | Geeft af en toe kapotte XML; krijgt daarom een tweede poging. |
| Take-Two IR | RSS | Gefilterd op Rockstar-titels: hier komt ook NBA 2K, Zynga en WWE langs. |
| X / @RockstarGames | `api.fxtwitter.com`, alleen de tweetteller | Zie hieronder. |

**X levert géén tekst.** De inhoud van tweets is sinds de API-wijzigingen niet
gratis op te halen: Nitter is dood, de publieke RSS-bruggen zijn dood, en de
embed-endpoint van X geeft direct `429`. De officiële API kost $200/maand. Wat
wel werkt is de tweetteller van het profiel; loopt die op, dan gaat er een ping
uit met een link naar het account. Ga hier niet naar zoeken alsof het een bug is.

## Beslissingen die je niet moet terugdraaien

**De GitHub-cron staat bewust laag (elke 6 uur).** Hij stond eerst op `*/5`.
Gemeten over 62 uur leverde dat **21 runs op in plaats van 743** — 3%, met gaten
tot 5,5 uur. GitHub knijpt geplande workflows op gratis accounts af en geeft
hoogfrequente schema's de laagste prioriteit. De runs blijven groen, dus je ziet
het niet aan de interface. Snelheid komt van de Mac, niet van GitHub.

**De repo is publiek.** Niet uit onachtzaamheid: op een privé-repo kost elke 5
minuten draaien ~8.600 Actions-minuten per maand tegen 2.000 gratis, en dan valt
hij rond dag 7 van elke maand stil. Gevolg: **nooit credentials in deze repo.**

**Het runnummer staat in `.run_no`, niet in de state.** Zat het in
`monitor_state.json`, dan veranderde dat bestand elke run en gaf elke run een
commit — op de Mac 1440 per dag.

**Een mislukt appje telt niet als verstuurd.** `requeue()` draait de
state-wijziging terug zodat de volgende run het opnieuw probeert, en de run
eindigt met exitcode 1. Zonder dat blijft een item als gemeld staan terwijl het
appje nooit aankwam — en dat is precies de storing die je nooit opmerkt.

**Log nooit een `requests`-exceptie rechtstreeks.** De tekst bevat de volledige
URL, inclusief `?apikey=...`, en Actions-logs zijn hier openbaar.

## Credentials

| Waar | Wat |
|---|---|
| `~/.config/rockstar-monitor/env` (Mac, chmod 600, buiten de repo) | `WHATSAPP_PHONE`, `WHATSAPP_APIKEY` |
| GitHub → Settings → Secrets → Actions | dezelfde twee |

GitHub-secrets zijn alleen schrijfbaar; je kunt ze niet uitlezen om ze elders in
te vullen.

## Testen

```bash
python rockstar_monitor.py --test          # stuurt één testappje
DRY_RUN=true python rockstar_monitor.py    # detecteert alles, stuurt niets
```

Gebruik `--test` altijd als eerste stap bij "ik krijg niets binnen". Stilte is
namelijk het normale gedrag: Rockstar publiceert twee à drie keer per week, en
GTA VI-nieuws zelden. *Geen appje* en *kapot* zien er identiek uit.

**Verreweg de meest voorkomende oorzaak:** CallMeBot pauzeert accounts geregeld.
Je ziet dan `HTTP 208` en in de body *"Your Account is Paused"*. De oplossing is
dat **Dennis zelf** het woord `resume` naar +34 623 78 64 49 stuurt via WhatsApp;
dat kan niet vanaf hier en de bestaande apikey blijft geldig.

## Vanuit de cloud

Een cloudsessie kan bij deze repo en bij GitHub Actions, maar **niet bij de Mac**.
Dus wel: code wijzigen, workflow aanpassen, Actions-logs lezen, dry runs draaien.
Niet: launchd herstarten, `~/Library/Logs/rockstar-monitor.log` lezen, of het
env-bestand aanpassen. Vraag Dennis om die stappen, of om de log te plakken.

De launchd-opzet staat in `mac/`, de installatie in de README.

## Status bij het schrijven (24-09-2026)

Draait sinds 21-09. Mediaan interval op de Mac 61 seconden; de enige onderbreking
was een nacht waarin de Mac sliep, door GitHub opgevangen. Nul appjes verstuurd,
want Rockstar heeft sinds 17-09 niets gepubliceerd — dat is correct gedrag, geen
storing. De macOS-upgrade naar Darwin 27 heeft launchd niet gesloopt.

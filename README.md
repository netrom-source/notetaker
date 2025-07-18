# Notator

Notator er et minimalistisk skriveprogram skrevet i Python og PyQt6. Programmet er designet til batteridrevne enheder som Raspberry Pi 3a+ og styres primært med tastaturet.

## Funktioner
- Mørk brugerflade og Markdown-highlighting direkte i editoren
- Automatisk genskabelse af seneste session med faner og zoomniveau
- Nye filer navngives automatisk med tidsstempel og gemmes i `data/`
- Første gang der gemmes kan filen omdøbes via `Ctrl+S`
- Auto-gem af åbne noter hvert tiende sekund
- Indbygget timer med presets (30 sek, 3, 7 og 11 min) og brugerdefineret tid
- Hemingway Mode som forhindrer sletning og baglæns navigation
- Knappen til Hemingway Mode findes i statuslinjen
- UI-skalering med `Ctrl++` og `Ctrl+-`
- Fanelinje kan skjules med `Ctrl+Alt+.`
- Fanelinjen viser en grøn bjælke under den aktive fane
- Live-rendering af Markdown-overskrifter direkte i teksten
- Timerens menu glider ned under tidtagningen og vælgeren kan betjenes med tastatur
- Alle tekster bruger JetBrains Mono eller nærmeste tilgængelige monospace-font
- Timer-menuen kan lukkes med `Esc` og bevarer fokus i menuens valg
- Tabbar og timer-menu skjules med glidende animationer
- Statuslinjen har afrundede hjørner og skygge for bedre læsbarhed
- Timeren blinker rødt når tiden er udløbet
- Åbn og gem foregår i en menu der glider op fra bunden
- Scrollbars har et enkelt, fladt design


## Tastaturgenveje
| Handling | Genvej |
|----------|-------|
| Ny note | `Ctrl+N` |
| Åbn fil | `Ctrl+O` |
| Gem | `Ctrl+S` |
| Gem som | `Ctrl+Shift+S` |
| Luk fane | `Ctrl+W` |
| Næste/forrige fane | `Ctrl+.`, `Ctrl+,` |
| Skjul fanelinje | `Ctrl+Alt+.` |
| Start timer | `Ctrl+T` |
| Reset/stop timer | `Ctrl+R` |
| Hemingway Mode | `Ctrl+H` eller knappen i statuslinjens højre side |
| Zoom ind/ud | `Ctrl++`, `Ctrl+-` |

Alle genveje oprettes som *ApplicationShortcut*, hvilket betyder at de virker
globalt i programmet uanset hvilket felt der har fokus.

Dobbelttryk `Ctrl+R` inden for to sekunder stopper timeren helt.

## Brug
Kør programmet med:
```bash
python3 main.py
```
Programmet forsøger at starte i fuldskærm og genskaber automatisk tidligere åbnede noter.

## Begrænsninger
- Programmet kræver at Qt-platform pluginnet `xcb` er installeret for at køre under X11. På nogle systemer kan dette mangle og forhindre opstart.
- Der er ingen forsøg på konfliktløsning hvis to processer redigerer den samme fil samtidigt.

## Ændringer
- 18-07-2025: Filnavnet kan nu ændres ved første gem, Hemingway-knappen er flyttet til statuslinjen og timer-menuen er integreret med slide-animation.
- 18-07-2025: Forbedret timer-navigation, fontvalg med fallback og moderne statuslinje.
- 18-07-2025: Timeren blinker ved udløb og fil-dialogerne er erstattet af indbyggede menuer.



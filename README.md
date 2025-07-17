# Notator

Notator er et minimalistisk skriveprogram skrevet i Python og PyQt6. Programmet er designet til batteridrevne enheder som Raspberry Pi 3a+ og styres primært med tastaturet.

## Funktioner
- Mørk brugerflade og Markdown-highlighting direkte i editoren
- Automatisk genskabelse af seneste session med faner og zoomniveau
- Nye filer navngives automatisk med tidsstempel og gemmes i `data/`
- Auto-gem af åbne noter hvert tiende sekund
- Indbygget timer med presets (30 sek, 3, 7 og 11 min) og brugerdefineret tid
- Hemingway Mode som forhindrer sletning og baglæns navigation
- UI-skalering med `Ctrl++` og `Ctrl+-`
- Fanelinje kan skjules med `Ctrl+Alt+.`
- Live-rendering af Markdown-overskrifter direkte i teksten

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
| Hemingway Mode | `Ctrl+H` eller knappen i øverste højre hjørne |
| Zoom ind/ud | `Ctrl++`, `Ctrl+-` |

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


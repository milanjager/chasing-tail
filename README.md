# Chasing Your Tail – detektor sledování na Raspberry Pi

Pasivně poslouchá Wi-Fi a Bluetooth zařízení v okolí, zaznamenává je s GPS
polohou a upozorní vás, když vás některé následuje přes více míst. Telefon a
hodinky jedné osoby spojí do jedné „osoby“, takže přijde jedno upozornění, ne dvě.

Inspirováno videem Davida Bombala *How to Track the People Tracking YOU* a
open-source nástrojem Chasing Your Tail.

```
 Wi-Fi (ALFA, monitor mode) ─┐
 Bluetooth LE ───────────────┼─► SQLite ─► analýza (skóre + seskupení) ─► upozornění
 GPS (gpsd) ─────────────────┘                     │                       (ntfy, desktop, log)
                                                   └─► webový dashboard s mapou
```

## Vyzkoušení bez hardwaru

Na libovolném počítači s Pythonem 3.10+:

```bash
pip install pyyaml flask pytest
```

```bash
python -m demo.demo
```

```bash
python -m demo.demo_web
```

Druhý příkaz spustí dashboard na http://localhost:5000 se simulací:
10 minut doma (pak se okolí odruší), potom dvouhodinová procházka Prahou
se 150 kolemjdoucími, sousedem v kavárně, sledující osobou s telefonem a
hodinkami a skrytým BLE trackerem. `python -m demo.demo --bez-odruseni`
ukáže, že bez odrušení vypadají jako „sledující“ hlavně vaše vlastní zařízení.

```bash
python -m pytest -q
```

## Instalace na Raspberry Pi

1. Nahrajte Raspberry Pi OS (64-bit, Bookworm), zapněte SSH a připojte
   Pi k síti přes vestavěnou Wi-Fi.
2. Připojte ALFA adaptér a GPS (viz [docs/HARDWARE.md](docs/HARDWARE.md)).
3. Zkopírujte projekt do Pi a spusťte:

```bash
sudo ./install.sh
```

Skript nainstaluje závislosti, nastaví gpsd, vygeneruje heslo k dashboardu
a spustí dvě služby: `chasing-tail` (skener) a `chasing-tail-web` (dashboard).

4. Otevřete `http://<ip-pi>:5000`, přihlaste se jako `admin` s heslem z instalace.
5. **Odrušte okolí.** Nechte Pi pár minut běžet doma v klidu a v dashboardu
   klikněte na *Ignorovat vše současné*. Váš telefon a hodinky, router,
   televize i zařízení sousedů se tím přestanou vyhodnocovat, podobně jako
   při hledání štěnic. Jednotlivá zařízení můžete ignorovat i tlačítkem
   *Ignorovat* u osoby a vrátit je v *Seznamu ignorovaných*.
6. Volitelně doplňte do `/opt/chasing-tail/config.local.yaml` hodnotu
   `alerts.ntfy_topic` pro upozornění na telefon (aplikace ntfy, odběr stejného tématu).

## Struktura

| Cesta | Obsah |
|---|---|
| `daemon/` | skenery Wi-Fi/BT, GPS, databáze, analýza, upozornění, hlavní smyčka |
| `web/` | Flask dashboard (osoby, mapa, upozornění) |
| `demo/` | generátor simulovaných dat a ukázky |
| `tests/` | testy (pytest) |
| `systemd/`, `scripts/`, `install.sh` | nasazení na Pi |
| `docs/` | [hardware](docs/HARDWARE.md), [algoritmus](docs/ALGORITMUS.md), [právní poznámky](docs/PRAVNI.md), [projektová dokumentace (Word)](docs/Projektova_dokumentace.docx), [prezentace (PowerPoint)](docs/Prezentace.pptx) |

## Užitečné příkazy na Pi

```bash
journalctl -u chasing-tail -f
```

```bash
sudo systemctl restart chasing-tail
```

```bash
cgps -s
```

(`cgps` ukazuje, jestli má GPS zaměření.)

## Omezení

Moderní telefony randomizují MAC adresy. Doma vypadá každé zařízení v okolí
jako „pořád přítomné“. Ve veřejné dopravě se mohou objevit falešné poplachy.
Podrobnosti najdete v [docs/ALGORITMUS.md](docs/ALGORITMUS.md#5-omezení).
Nástroj slouží k ochraně vlastního soukromí, ne ke sledování jiných, viz
[docs/PRAVNI.md](docs/PRAVNI.md).

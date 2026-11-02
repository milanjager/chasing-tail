# Hardware

Vše se připojuje přes USB, bez pájení a bez GPIO.

## Seznam dílů

| Díl | Doporučení | Proč |
|---|---|---|
| Počítač – domácí | Raspberry Pi 4 Model B (2 GB) nebo Pi 5 | Výkon na analýzu i dashboard, 4× USB |
| Počítač – kapesní | Raspberry Pi Zero 2 W + USB OTG hub | Malý, nízká spotřeba |
| Wi-Fi adaptér | ALFA AWUS036ACM (čip MT7612U) | Monitor mode s ovladačem přímo v jádře, bez kompilace |
| GPS | USB přijímač u-blox (např. VK-162 / VK-172) | Funguje hned jako `/dev/ttyACM0` s gpsd |
| Bluetooth | Vestavěný v RPi; volitelně USB BT 5.x dongle | Externí dongle s anténou má větší dosah |
| Paměť | microSD 32 GB, třída A1 | Databáze má po 14 dnech řádově desítky MB |
| Napájení – doma | Oficiální zdroj RPi (5 V / 3 A, u Pi 5 5 V / 5 A) | ALFA adaptér má proudové špičky |
| Napájení – venku | Powerbanka 10 000 mAh s USB-C PD | Pi 4 + ALFA + GPS odebírají zhruba 3–5 W, tj. přibližně 6–9 hodin |
| Krabička | Vlastní 3D tisk nebo plastová instalační krabička | Otvor pro anténu ALFA, větrání |

> ALFA AWUS036ACH (na videu) funguje také, ale potřebuje ovladač `rtl8812au`
> kompilovaný mimo jádro, a ten se po aktualizaci jádra může rozbít. Proto doporučuji ACM.

## Zapojení

```
            ┌──────────────────────────┐
            │      Raspberry Pi 4      │
            │                          │
 ALFA ACM ──┤ USB 3 (modrý)            │
 GPS u-blox ┤ USB 2                    │
 (BT dongle)┤ USB 2  (volitelné)       │
            │                          │
 napájení ──┤ USB-C                    │
            │  wlan0 = vestavěná Wi-Fi │ → připojení k síti / hotspot pro dashboard
            │  wlan1 = ALFA            │ → monitor mode (jen poslech)
            └──────────────────────────┘
```

- **wlan0** (vestavěná Wi-Fi) zůstává normálně připojená, abyste se dostali na dashboard.
- **wlan1** (ALFA) je v monitor mode a nic nevysílá.
- GPS přijímač dejte co nejvýš a mimo kovový kryt. První zaměření venku trvá 1–5 minut.

## Kapesní varianta (Pi Zero 2 W)

Zero 2 W má jediný datový micro-USB port, takže potřebujete malý USB hub
(ideálně s externím napájením, protože ALFA má špičky přes 500 mA).
Dashboard pak otevřete v telefonu, který je připojený k hotspotu Pi
nebo Pi k hotspotu telefonu.

## Domácí varianta

Pi umístěte ke vchodu nebo k oknu do ulice. V domácím režimu se nemění
poloha, takže skóre stojí jen na čase (jak dlouho a opakovaně je zařízení
poblíž). Po instalaci proto v dashboardu odrušte okolí tlačítkem
*Ignorovat vše současné*, jinak budou vaše zařízení a zařízení sousedů
vždy vypadat podezřele.

# Jak detekce funguje

## 1. Sběr dat

| Zdroj | Co se zaznamená | Jak |
|---|---|---|
| Wi-Fi | MAC adresa z *probe requestů*. Telefon jimi hledá známé sítě | `scapy`, monitor mode, přepínání kanálů 1–13 |
| Bluetooth LE | MAC adresa z reklamních paketů (hodinky, sluchátka, trackery) | `bleak`, sken 5 s každých 10 s |
| GPS | Vaše poloha v okamžiku záznamu | `gpsd` |

Ukládá se jen MAC, síla signálu, čas a vaše poloha. Obsah komunikace se nezachytává.

## 2. Skóre podezřelosti (0–1)

Analýza běží každou minutu nad posledními 2 hodinami.

- **time_ratio**: v kolika časových oknech (2 min) bylo zařízení vidět, děleno
  počtem oken v období.
- **location_ratio**: na kolika z vašich míst (buňky GPS přibližně 100 m) bylo vidět,
  děleno počtem míst, kde jste byli.

```
pohybujete se (≥ 2 místa):  skóre = 0,4 · time_ratio + 0,6 · location_ratio
stojíte (doma, bez GPS):    skóre = time_ratio
```

Práh pro upozornění je 0,55. Kolemjdoucí mají skóre kolem 0,1. Soused, který
sedí hodinu ve stejné kavárně, má kolem 0,2, protože ho vidíte jen na jednom
místě. Kdo jde s vámi přes celé město, má přes 0,8.

## 3. Seskupení zařízení do osob

Telefon a hodinky jedné osoby by jinak vyvolaly dvě upozornění. Proto se
zařízení, která se **objevují a mizí současně**, spojí do jedné osoby.

Dvě zařízení se spojí, pokud:

1. sdílejí aspoň **5** časových oken, **a zároveň**
2. **korelace přítomnosti phi ≥ 0,5**: když jedno vypadne z dosahu, vypadne i
   druhé, **nebo**
3. **Jaccard ≥ 0,9**: obě jsou vidět skoro pořád (tehdy se phi spočítat nedá).

Spojování je tranzitivní: když telefon patří k hodinkám a hodinky ke
sluchátkům, jsou všechna tři jedna osoba. Skóre osoby je nejvyšší skóre jejích
zařízení. Upozornění chodí jednou na osobu, nejvýš jednou za 30 minut.

### Proč phi a ne jen Jaccard

Jaccard měří jen to, jak často jsou zařízení vidět současně. Dvě nesouvisející
zařízení, která jsou poblíž 70 % času, mají Jaccard přes 0,5 jen náhodou.
Phi navíc počítá, jestli zařízení **chybí** současně, takže nesouvisející
zařízení mají phi kolem 0. V testovacích datech vychází phi pro telefon s hodinkami
0,7–0,9 a pro nesouvisející tracker pod 0,2.

### Proč 2minutová okna

Telefony posílají probe requesty nepravidelně, často jednou za minutu nebo méně.
S 1minutovými okny skončí telefon a hodinky jedné osoby často v sousedních
oknech, takže úspěšnost seskupení byla v simulaci jen 21 %. Při 2 minutách byla 98 %.
Při 3 a více minutách se už začínaly slučovat i nesouvisející
zařízení. Když 2minutová okna selžou, zařízení zůstanou oddělená. Přijdou tedy dvě
upozornění místo jednoho, ale chybné sloučení nenastane.

## 4. Odrušení okolí

Váš vlastní telefon a hodinky jsou s vámi pořád a na všech místech, takže
by bez úprav měly nejvyšší skóre ze všech. Doma navíc pořád vidíte router,
televizi a zařízení sousedů. Proto se nejdřív odruší známé okolí, podobně
jako při hledání štěnic:

1. Zapněte Pi tam, kde jste v klidu a kolem jsou jen známá zařízení (doma).
2. Po pár minutách klikněte v dashboardu na **Ignorovat vše současné**.
   Všechna zařízení viděná za zvolenou dobu (2 min až 1 h) se uloží na
   seznam ignorovaných se zdrojem „odrušení“.
3. Vyrazte. Vyhodnocuje se jen to, co přibude.

Další možnosti:

- Tlačítko **Ignorovat** u osoby v přehledu ignoruje všechna její zařízení.
- V **Seznamu ignorovaných** lze zařízení vrátit nebo ručně přidat MAC s popisem.
- **Zrušit odrušení** smaže položky z odrušení, ručně přidané zůstanou.
- `analysis.ignore_macs` v konfiguraci je trvalý seznam pro pokročilé.

Ignorovaná zařízení se nezapočítávají do skóre ani do seskupení a neposílají
upozornění. Jejich záznamy se ale dál ukládají, takže po vrácení ze seznamu
se zařízení vyhodnotí i se svou historií. Zápisy přes dashboard přijímají jen
JSON, aby cizí webová stránka nemohla přes váš prohlížeč detektor „oslepit“
tím, že by ignorovala všechno.

## 5. Omezení

- **Randomizace MAC.** iOS 14+ a Android 10+ posílají probe requesty z náhodné
  MAC, která se mění. Dlouhodobé sledování přes Wi-Fi je proto méně spolehlivé.
  Dashboard randomizované MAC označuje.
- **Statická zařízení.** Doma se všechno kolem tváří jako „pořád přítomné“.
  Řešením je odrušení okolí (kapitola 4).
- **Odrušení a náhodné MAC.** Telefon s náhodnou MAC si adresu časem změní a
  pak se objeví jako nové zařízení. Odrušení je proto dobré občas zopakovat.
- **Dvě nezávislá zařízení stále poblíž** (např. tracker v tašce a sledující, který
  nikdy nevypadne z dosahu) od sebe podle času odlišit nejde a mohou se spojit.
- **Falešné poplachy** ve veřejné dopravě: spolucestující ve stejném vagonu
  mají vysoké skóre. Rozhodují místa: po vystoupení by skóre mělo klesnout.
- Nástroj **nenahrazuje** profesionální protisledovací prověrku.

## 6. Ladění

Všechny prahy jsou v `config.yaml` v sekci `analysis`. Po změně restartujte
službu: `sudo systemctl restart chasing-tail`.

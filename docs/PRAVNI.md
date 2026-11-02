# Právní a etické poznámky

*Nejde o právní radu. Pokud zařízení chcete používat jinak než soukromě, poraďte se s právníkem.*

- **MAC adresy jsou osobní údaje** podle GDPR, protože mohou identifikovat
  zařízení konkrétní osoby.
- Pro **čistě osobní nebo domácí činnost** se GDPR neuplatní (čl. 2 odst. 2 písm. c).
  Ochrana vlastní osoby před sledováním do této výjimky obvykle spadá.
  Zveřejnění dat nebo jejich použití ke sledování jiných do ní nespadá.
- Nástroj **jen pasivně poslouchá** veřejně vysílané identifikátory. Nic nevysílá,
  nikam se nepřipojuje a nečte obsah komunikace.
- Nástroj **nepoužívejte ke sledování jiných lidí.** To může být trestný čin
  nebezpečného pronásledování (§ 354 trestního zákoníku).

## Co projekt dělá pro ochranu soukromí

- Data se ukládají jen lokálně na SD kartu v Pi.
- Záznamy starší než 14 dní se automaticky mažou (`database.retention_days`).
- Dashboard je chráněný heslem. Bez hesla se nespustí, pokud je dostupný ze sítě.
- Notifikace (ntfy, Pushbullet) jsou vypnuté, dokud je sami nenastavíte. Odesílá
  se v nich jen zkrácený text s MAC adresou.

Pokud máte podezření, že vás někdo skutečně sleduje, obraťte se na Policii ČR (158).

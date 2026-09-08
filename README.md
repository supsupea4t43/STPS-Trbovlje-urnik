# Urnik STPŠ

Namizna aplikacija za Windows, ki prikazuje tedenski urnik [STPŠ Trbovlje](https://www.stps-trbovlje.si/urniki/)
— za **vse oddelke**, skupaj z **nadomeščanji**, **zaposlitvami** in **odpadlimi urami**.

Zažene se kot samostojno okno (brez brskalniških zavihkov in orodnih vrstic), veliko
natanko toliko, kot ga zahteva urnik — brez drsnikov. Pripeti ga je mogoče v meni Start.

## Namestitev

Potreben je Python 3 in Microsoft Edge. Če Pythona ni, ga skripta ponudi
namestiti prek `winget`.

```bash
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Skripta ustvari bližnjico **Urnik STPŠ** v meniju Start. Windows od različice 10
ne dovoli programskega pripenjanja, zato je zadnji korak ročen:

> Tipka Windows → vtipkaj `Urnik STPŠ` → desni klik → **Pripni na začetni zaslon**

Dodatne možnosti:

```bash
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Desktop
```

```bash
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Remove
```

## Namestitev na drug računalnik

Aplikacija ni vezana na noben določen računalnik — v njej ni nobene
absolutne poti.

**Zeleni gumb „Code“ → „Download ZIP“**, razširi mapo, nato dvoklikni
**`Namesti.bat`**. Ta požene `install.ps1` mimo pravil za skripte
PowerShell, po potrebi namesti Python in ustvari bližnjico.
Kratka navodila so tudi v `ZAZENI.txt`.

Kdor uporablja git:

```bash
git clone https://github.com/<uporabnik>/<repo>.git
```

Mape po namestitvi naj se ne premika: bližnjica kaže nanjo. Če se premakne,
je dovolj znova pognati `Namesti.bat`.

Podatki so za vsakega uporabnika svoji (`%LOCALAPPDATA%\STPS-Urnik`),
skrbniške pravice niso potrebne.

Za primere brez GitHuba (USB, priponka) naredi samostojen paket s
`pack.ps1` — ta zloži le tisto, kar aplikacija res potrebuje.

## Uporaba

Okno pokaže cel teden izbranega oddelka. Današnji dan je obrobljen modro.
Ob sobotah in nedeljah se samodejno pokaže že naslednji teden.

Oznake ur:

| Oznaka | Pomen |
| --- | --- |
| `NAD` | Nadomeščanje |
| `ZAP` | Zaposlitev |
| `ODP` | Odpadla ura oz. ni bilo pouka (predmet je prečrtan) |
| `DOG` | Dogodek ali šolski koledar (npr. športni dan, počitnice) |
| `2` | Več skupin pri isti uri — prikazane so vse |

Zaporedne ure z enako vsebino so združene v en blok, zato se dvourni bloki in
celodnevni dogodki ne ponavljajo pri vsaki uri.

Tipke: `←` `→` prejšnji/naslednji teden, `T` nazaj na tekoči teden, `R` osveži.
Urnik se sicer osveži sam vsakih pet minut in ob vsakem prehodu okna v ospredje.

Izbrani oddelek se zapomni za naslednji zagon. Shrani ga strežnik
(`/api/prefs`), ne brskalnik: strežnik ob vsakem zagonu dobi druga vrata,
s tem pa je drugo tudi izvorišče strani in `localStorage` prejšnjega zagona
ne bi bil viden.

## Kako deluje

Šolska stran vgradi eAsistentov javni urnik. Aplikacija ta vir bere neposredno:

1. s šolske strani prebere eAsistentov *hash* šole (zato preživi njegovo menjavo),
2. iz javne strani urnika prebere seznam oddelkov in tekoči teden,
3. urnik posameznega tedna dobi prek `ajax_urnik`.

Ker se ID-ji oddelkov ob novem šolskem letu spremenijo, se seznam oddelkov bere
sproti in ni nikjer zapisan na trdo.

Odgovori se shranjujejo v `%LOCALAPPDATA%\STPS-Urnik\cache.json`. Če ni povezave,
aplikacija pokaže zadnji shranjeni urnik in to jasno označi.

Zagon odpre majhen strežnik na `127.0.0.1` (naključna vrata, dosegljiv samo s tega
računalnika) in okno Edge v načinu aplikacije. Ko okno zapreš, se strežnik po
minuti sam ugasne. Drugi zagon ne podvoji programa, ampak odpre novo okno.

Vmesnik po izrisu izmeri, koliko prostora vsebina potrebuje, prilagodi okno in mero
sporoči strežniku (`/api/size`), da je pravšnja že ob naslednjem zagonu.

Poleg urnika je na voljo še `/api/nadomescanja?date=YYYY-MM-DD` — seznam nadomeščanj
za celo šolo. V vmesniku ni prikazan, ker so nadomeščanja vidna že v sami mreži.

## Datoteke

| Datoteka | Vloga |
| --- | --- |
| `stps_urnik.py` | Zagon, lokalni strežnik, API, predpomnilnik |
| `urnik_source.py` | Branje in razčlenjevanje eAsistentovega urnika |
| `web/` | Vmesnik (HTML, CSS, JS) |
| `make_icon.py` | Izdela `assets/urnik.ico` in `web/icon.svg` |
| `install.ps1` | Bližnjica v meniju Start, po potrebi namesti Python |
| `Namesti.bat` | Dvoklik za prejemnika — požene `install.ps1` |
| `pack.ps1` | Zapakira aplikacijo v `Urnik-STPS.zip` za prenos |
| `ZAZENI.txt` | Navodila v paketu za prejemnika |

Uporabljena je samo standardna knjižnica Pythona — ni česa nameščati.

## Razvoj in preverjanje

```bash
python stps_urnik.py --no-browser --port 8777
```

```bash
python stps_urnik.py --danes "3. A"
```

Vedenje ob koncu tedna se da preveriti brez čakanja — parameter `datum` podtakne
drug „danes“:

```bash
start http://127.0.0.1:8777/?datum=2026-09-05
```

# Urnik STPŠ

Namizna aplikacija za Windows, ki prikazuje tedenski urnik [STPŠ Trbovlje](https://www.stps-trbovlje.si/urniki/)
— za **vse oddelke**, skupaj z **nadomeščanji**, **zaposlitvami** in **odpadlimi urami**.

Zažene se kot samostojno okno (brez brskalniških zavihkov in orodnih vrstic), veliko

**Namestitev**

1. Code → Download ZIP, exstraktiraj mapo
2. Dvoklikni `Namesti.bat`. Če Pythona še ni, ga namesti sam.
3. Tipka Windows, napiši `Urnik STPŠ`, desni klik → Pripni na začetni zaslon

Rabiš Windows 10 ali 11 in Edge. Mape potem ne premikaj, ker bližnjica kaže nanjo. Če jo že premakneš, samo še enkrat poženeš `Namesti.bat`.

**Uporaba**

Oddelek izbereš zgoraj levo, med tedni skačeš s puščicama. `T` te vrne na tekoči teden, `R` osveži. Današnji dan je obrobljen modro, čez vikend pa se odpre kar naslednji teden.

Oznake: `NAD` nadomeščanje, `ZAP` zaposlitev, `ODP` odpadla ura, `DOG` dogodek. Številka pomeni, da je pri isti uri več skupin.

**Kako dela**

Šolska stran ima urnik samo vgrajen z eAsistenta, zato program bere kar ta vir in ne strga same strani. Hash šole in seznam oddelkov prebere sproti, tako da preživi menjavo hasha in nove ID-je oddelkov ob novem šolskem letu.

Ob zagonu se požene majhen strežnik na 127.0.0.1 (vsakič druga vrata) in odpre Edge v načinu aplikacije. Stran se sama izmeri in okno prilagodi vsebini, mero pa sporoči nazaj, da je naslednjič prava že takoj. Ko zapreš okno, se strežnik čez minuto ugasne sam.

Odgovori se shranjujejo v `%LOCALAPPDATA%\STPS-Urnik`. Brez interneta pokaže zadnji shranjeni urnik in to tudi napiše. Izbrani oddelek si zapomni strežnik in ne brskalnik, ker so vrata ob vsakem zagonu druga in bi bil `localStorage` vsakič prazen.

Napisano je samo s standardno knjižnico Pythona, tako da ni treba nič dodatno nameščati.

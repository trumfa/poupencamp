# POUPE Encamp, en clar

Consulta ciutadana del Pla d'Ordenació i Urbanisme de la Parròquia d'Encamp, unitat
d'actuació per unitat d'actuació, en llenguatge planer i amb l'article de la norma a cada punt.

**Web independent, feta a títol particular.** No és una web oficial ni té cap valor
administratiu: no substitueix cap certificat urbanístic ni cap consulta oficial. Pot contenir
errors. L'únic text que preval és el publicat al BOPA.

---

## Com està muntat

Dues peces, i cadascuna té un sol ofici:

| Peça | Què hi ha | Qui la toca |
|---|---|---|
| **El full de càlcul** | Tot: les pestanyes de la base de dades (`Fitxes`, `Parametres`, `UA`, `Normativa`, `Claus`…), que surten de l'extracció per OCR, i les de contingut (`config`, `textos_web`, `valors_public`…), que diuen com s'explica cada cosa | Les de contingut, tu. Les de la base de dades, el procés d'extracció |
| **Aquest repositori** | La pàgina i el guió que llegeix el full | Només si es canvia el disseny o la lògica |

El guió `scripts/build-data.mjs` llegeix les pestanyes del full, les creua i escriu `public/data.json`.
La pàgina és un sol fitxer estàtic que llegeix aquest JSON. No hi ha servidor, ni base de dades,
ni cap dependència de npm.

```
scripts/build-data.mjs      llegeix el full -> public/data.json + public/index.html
scripts/config.mjs          identificador del full i pestanyes que llegeix
scripts/converteix-planols.py  PNG del Drive -> WebP per a public/planols/
scripts/dwg-a-mapa.py       DWG cadastral -> data/mapa.json (perímetres de les unitats)
data/mapa.json              geometria del plànol interactiu
src/index.html              la pàgina (cos del document; el build hi posa el <head>)
public/                     el que es publica
```

## Requisit previ: compartir el full

El build el llegeix sense credencials, així que ha d'estar compartit com a
**«Qualsevol amb l'enllaç · Lector»**. Amb això n'hi ha prou; no cal cap clau d'API ni cap
compte de servei. Si algun dia el tornes privat, el build fallarà amb un 401 i t'ho dirà.

L'identificador del full va a `scripts/config.mjs`, a la constant `FULL`. És el tros de la URL
entre `/d/` i `/edit`.

## Posar-ho en marxa

```bash
npm run build     # genera public/data.json i public/index.html
npm run serve     # obre http://localhost:8080
```

Per treballar sense connexió, exporta les pestanyes a CSV en una carpeta i fes
`POUPE_CSV=../csv npm run build`.

### Pujar-ho a GitHub

Descomprimeix la carpeta, entra-hi i:

```bash
git init -b main
git add .
git commit -m "Web del POUPE d'Encamp"
git remote add origin https://github.com/<usuari>/<repositori>.git
git push -u origin main
```

Són uns 96 MB, gairebé tot plànols. Hi caben de sobres: GitHub només es queixa a partir de
100 MB **per fitxer** (el plànol més gros fa 442 KB) i d'1 GB de repositori.

### Publicar-ho a Vercel

1. Puja aquest repositori a GitHub (just aquí sobre).
2. A Vercel, **Add New → Project → Import** el repositori.
3. Vercel ja llegeix `vercel.json`: comanda `npm run build`, sortida `public`. No cal tocar res.
4. **Deploy**.

### Que els canvis del full arribin a la web

El JSON es genera a cada desplegament, o sigui que n'hi ha prou amb tornar a desplegar:

- **A mà:** a Vercel, *Deployments → Redeploy*.
- **Automàtic:** a Vercel, *Settings → Git → Deploy Hooks*, crea un hook (branca `main`),
  copia la URL i posa-la a GitHub com a secret **`VERCEL_DEPLOY_HOOK`**
  (*Settings → Secrets and variables → Actions*). El workflow `Dades` la crida cada dia a les
  05:00 UTC, i també quan pitges *Run workflow* a mà.

El mateix workflow comprova, a cada push, que el full es llegeix i que en surten més de 100
unitats. Si algú trenca una capçalera del full, salta abans d'arribar a producció.

## Els plànols

**Ja hi són tots**, convertits: 492 plànols del Drive passats a WebP (1600 px d'amplada,
qualitat 80), 96 MB en comptes dels 330 MB dels PNG originals. Les 405 unitats en tenen, com a
mínim, un.

Venen a part, en quatre zips (`planols-1de4.zip` … `planols-4de4.zip`), perquè no cabien en un
sol enviament. **Descomprimeix-los tots dins de `public/planols/`**, sense subcarpetes, abans de
fer el primer commit. Han de quedar-hi 492 fitxers `.webp`.

La pàgina busca cada plànol a `public/planols/<id_fitxa>.webp` — per exemple
`public/planols/TORRENTS_DE_L_OBAC_1__III__M01.webp` — i el noms surten tal qual del Drive, o
sigui que no cal reanomenar res. Clicant la imatge s'obre a mida completa. Si un fitxer no hi és,
la pàgina ho diu i, si el full de dades en guarda l'identificador del Drive, ofereix el botó per
obrir-lo allà.

Quan surtin plànols nous o revisats, es tornen a convertir i es fa commit del resultat:

```bash
pip install pillow
python scripts/converteix-planols.py \
    --entrada /ruta/a/Planols_POUPE \
    --sortida public/planols
```

També es pot fer des de Google Colab muntant el Drive; la capçalera del guió porta les
instruccions.

## El plànol interactiu

A la portada, sota el cercador, hi ha el plànol de la parròquia: s'hi pot arrossegar i fer zoom
amb la roda o pessigant. Les unitats van pintades segons la classificació del sòl, i de prop en
surten els noms.

Amb ratolí, passar per sobre d'una unitat n'ensenya el nom i clicar-la obre la fitxa. Sense
ratolí no hi ha «passar per sobre», així que el primer toc ensenya el nom i el segon obre la
fitxa; la pàgina ho detecta amb `matchMedia('(hover: hover)')` i ajusta també el text d'ajuda.

A partir de 900 px d'amplada el plànol se surt de la columna de text i ocupa fins a 1.280 px:
triar una unitat damunt del mapa demana espai, mentre que la fitxa es llegeix millor estreta.

La geometria surt del DWG cadastral del Comú, que porta els perímetres de les unitats en capes
per classificació i els noms en una capa a part. `scripts/dwg-a-mapa.py` els creua i escriu
`data/mapa.json`, que el build incrusta dins de `data.json`. El DWG no es puja al repositori:
els navegadors no el saben llegir i pesa 3,5 MB; el que es publica és el JSON, simplificat al
metre i amb les coordenades desades com a deltes entre vèrtexs.

**Com es decideix quin recinte és de quina unitat.** El DWG porta tres senyals, i cap dels
tres no és infal·lible tot sol: la **superfície** escrita dins de cada recinte a la capa `_Sup UA`
(que coincideix amb l'àrea calculada amb un error mitjà de dues centèsimes per cent), el **nom**
de la unitat a la capa `ÀMBITS NOM` —que sovint cau fora del seu recinte, amb una línia de guia,
i el més proper sol ser el del veí gros— i la **qualificació**, que és la capa mateixa
(`01 1 UA SUC`, `01 2 UA SUNC`, `01 3 UA SUBLE`, `01 11 UA SUCc`). Les fitxes urbanístiques diuen
la superfície i la classificació de cada part.

Per això el guió no aplica una regla que mani sobre les altres, sinó que posa **una nota a cada
parella (part, recinte)**: com més baixa, més convincent. Es reparteix de la millor parella a la
pitjor i cap recinte no és de dues parts alhora.

- **La qualificació filtra.** Una part de SUNC no pot anar a parar a un recinte dibuixat a la capa
  de SUBLE. SUC i SUCc es deixen passar l'una per l'altra, però amb penalització.
- **La superfície mana quan hi és.** Si l'àrea del recinte coincideix amb la de la fitxa (±20%),
  la parella surt amb una nota d'entre 0 i 3, i aquestes es reparteixen primer.
- **El nom entra quan la superfície no pot.** Si el nom de la part és escrit dins del recinte i la
  qualificació encaixa, la parella val 3,5 encara que els metres no quadrin. Això recupera les
  unitats la fitxa de les quals porta la superfície mal escrita —Feda 4 diu «3.04» i el recinte fa
  3.032 m²—, i és el que arregla també les que abans es quedaven sense dibuix.
  Per no acceptar disbarats, el recinte no pot passar de quinze vegades la superfície de la fitxa.
- **Un nom a dins reserva.** Si dins d'un recinte hi ha el nom d'una sola unitat, i aquella unitat
  té una part d'aquella qualificació, les altres unitats el tenen penalitzat: només se'l queden si
  no els queda res més. Així un veí amb la superfície semblant no pot endur-se un recinte que porta
  el nom d'algú altre escrit a dins.
- **Unitats de diverses peces:** se sumen els recintes lliures del voltant, de la mateixa
  qualificació, fins a fer la superfície de la fitxa.
- **I una última xarxa:** el nom cau dins d'un recinte que no vol ningú més i no passa del doble ni
  baixa de la meitat del que diu la fitxa.

En surten **369 unitats dibuixades**, amb un error de superfície d'una mitjana del 0,5%.

Al final de l'execució, el guió llista les unitats on la superfície de la fitxa i la del dibuix no
s'assemblen. Gairebé sempre és la fitxa que la porta mal escrita —un punt de milers de menys— i es
corregeix al full. Les que ja s'han mirat una per una i es queden com són van al diccionari
`ACCEPTATS` del guió, amb el motiu, i deixen de sortir a l'informe: ara mateix hi ha Cresper (el
recinte gros del costat és del veí), Pardines 3 (un recinte per a cadascuna de les dues Pardines,
encara que els metres no quadrin) i Pas de la Casa 1 (la fitxa es queda curta).

`data/mapa.json` guarda també les 4.432 parcel·les del cadastre, però ara no es publiquen: el
plànol només ensenya les unitats. Per tornar-les a enviar al navegador, treu el `delete mapa.p`
de `scripts/build-data.mjs` i el dibuix del canvas.

**El sistema de coordenades.** El cadastre va en NTF (Paris) / Lambert Sud, `EPSG:27563`, que és
el sistema històric d'Andorra. El guió el passa a Web Mercator (`EPSG:3857`), que és el que fan
servir els mosaics de qualsevol proveïdor de mapes: així el dibuix quadra amb el fons sense cap
altre ajust.

**El mapa de fons.** Es tria amb els botons de dalt a l'esquerra: *Ortofoto* (World Imagery
d'Esri), *Mapa* (OpenStreetMap) o *Cap*. Tots dos són gratuïts i només demanen que se'n digui la
procedència, cosa que la pàgina fa a sota dels botons. Els mosaics es demanen directament amb
`<img>` i es dibuixen al canvas; no hi ha cap biblioteca de mapes. Per canviar de proveïdor n'hi
ha prou amb tocar l'objecte `FONS` de `src/index.html`; si algun dia es vol Google Maps, cal una
clau de l'API de Google amb facturació activada i fer servir el seu SDK, perquè les seves
condicions no permeten agafar-ne els mosaics pel seu compte.

De les 405 unitats, 369 tenen perímetre. Les 36 que falten es reparteixen entre les que el DWG
no dibuixa com a recinte d'unitat —àmbits grans de sòl no urbanitzable, concessions, refugis— i
unes quantes on la superfície de la fitxa i la del dibuix no s'assemblen prou per fiar-se'n. Es
troben igualment pel cercador. Per afegir-ne, n'hi ha prou
amb posar el nom com surt al DWG al diccionari `ALIES` del guió i tornar-lo a executar: així és
com les quatre estacions de servei, que al DWG són «E.S. Esso» i companyia, van a parar a les
unitats `ESSO`, `Figueredo`, `Mòbil` i `Arajol`.

La capa d'ortofoto del DWG és una referència externa i la imatge no és dins del fitxer; per això
el fons ve d'un servei de mosaics i no del DWG.

## Unitats amb més d'una fitxa

Una mateixa unitat pot sortir a dos volums del pla: el de la vall (o el dels Cortals, o el del
Pas de la Casa, o el de sòl urbanitzable) i el de sòl no urbanitzable. Quan passa, la unitat té
**dues fitxes amb dues classificacions**, dues superfícies, dos plànols i dos jocs de paràmetres.
Passa a 91 de les 405: per exemple Arenal (SUBLE de 36.848 m² al volum VI i SNUBLE de 104 m² al
VII), Nanta Alta 1 o Ajustants de Dalt 2.

Fins ara la web només n'ensenyava una i l'altra quedava amagada. Ara cada unitat guarda una
llista de **parts**, una per volum, i la fitxa comença amb un grup de botons per triar-ne una:
canviar de part canvia la classificació, la superfície, la clau, el plànol, el resum, els avisos
i tots els punts de la norma. Mentre no se'n triï cap val la primera, que és sempre la urbana
(la de sòl no urbanitzable va l'última). Els filtres de zona i subzona es buiden en canviar de
part, perquè les zones d'una no són les de l'altra.

Al plànol, cada part es reparteix pel seu compte: es busca el recinte que fa la superfície
d'aquella fitxa, no la de la unitat sencera. Això n'ha arreglat unes quantes que abans anaven a
parar al recinte del veí (Ajustants de Dalt 2, per exemple, és exactament el recinte de 4.423 m²).

Si una unitat de dues parts no diu la superfície d'una d'elles, aquella part es queda sense
superfície en comptes d'heretar la de la unitat sencera: repetir-la a totes dues enganyava el
lector i feia que el plànol la comptés dos cops.

Cada part porta el seu **tipus de fitxa**, tret de la fitxa i no de la unitat: Salitar és «UA per
subzona» a la part urbana i «àrea diferenciada» a la de sòl no urbanitzable.

A la pestanya `UA` del full, un parell d'unitats (Salitar, Lloset 2) tenen **una fila per volum**
en comptes d'una de sola. No són duplicats: són la mateixa unitat amb dues qualificacions. Com que
les parts surten de les pestanyes `Fitxes` i `Parametres`, el build es queda una fila per unitat
—la urbana, que és la que porta el nom que encapçala la fitxa— i les parts hi són igualment.

## Claus amb més d'un tipus

Alguna clau del pla no és una sola cosa. La subzona 11, per exemple, en són dues: la **11-A**
(unihabitatge i hotels) i la **11B** (hotels de natura), totes dues a l'article 78. Les fitxes
urbanístiques, però, diuen «Clau 11» a seques, i la web no pot endevinar quina toca.

La solució viu al full, no al codi: a `claus_public` cada tipus té la seva fila amb la columna
**`clau_mare`** apuntant a la clau que surt a la fitxa, i els valors de `valors_public` van a la
clau concreta (`11A`, `11B`), no a la mare. Quan una unitat porta una clau amb tipus, la pàgina hi
posa un grup de botons perquè l'usuari triï; mentre no en triï cap val el primer.

Funciona igual per a qualsevol altra clau: n'hi ha prou amb omplir `clau_mare`. Ara ho aprofiten
la subzona 11 i les unitats la fitxa de les quals diu «Subzona 5», «7» o «8» sense concretar-ne la
lletra.

## Què queda per fer

- **Cerca per referència cadastral.** La pestanya `Cadastre` del full de dades encara és buida.
- **Revisar els textos planers.** A `valors_public` i `claus_public` la majoria de files encara
  tenen `revisat = NO`: són redaccions fetes llegint la norma, però sense validar una per una.
  Cada frase corregida es propaga a totes les unitats que fan servir aquella clau.

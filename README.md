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
| **El full de càlcul** | 19 pestanyes en tres famílies: la **font** (`documents`, `fitxes`, `unitats`, `recintes`), la **norma** (`articles`, `apartats`, `claus`, `claus_parametres`, `proteccions`…) i el **contingut públic** (`config`, `textos`, `blocs`, `parametres`, `avisos`, `glossari`, `capes`) | Les de contingut, tu. Les altres, l'extracció i el plànol |
| **Aquest repositori** | La pàgina, el guió que llegeix el full i la geometria del plànol | Només si es canvia el disseny o la lògica |

```
scripts/build-data.mjs      llegeix el full -> public/data.json, index.html i esquema.html
scripts/config.mjs          identificador del full i pestanyes que llegeix
scripts/planol-nou.py       un plànol nou (GeoJSON o DWG) -> recintes.csv + geometria
scripts/migra-full.py       del full vell de 27 pestanyes al nou de 19
scripts/mira-pestanya.mjs   ensenya com el build veu una pestanya, per quan es queixa
scripts/converteix-planols.py  PNG del Drive -> WebP per a public/planols/
data/geometria.json         el dibuix, una entrada per recinte
data/recintes.geojson       el mateix en format obert, per a qui el vulgui obrir
src/index.html              la pàgina (cos del document; el build hi posa el <head>)
src/esquema.html            «Qui regula què»: quin nivell del pla decideix cada paràmetre
src/recintes.html           eina interna per assignar els recintes del plànol a les unitats
public/                     el que es publica
```

### Les tres regles de l'estructura

1. **Cada dada, en un sol lloc.** La classificació és de la fitxa, no de la unitat; la
   superfície també. La unitat només té identitat: identificador, nom i àlies.
2. **Res no s'esborra mai.** Una modificació del pla no és una edició: és una fitxa nova, i la
   vella es queda amb `vigent = NO` i la data en què ho va deixar de ser. Igual amb les unitats
   (`estat`) i els recintes.
3. **El full decideix, el codi no endevina.** Quin recinte del plànol és de quina unitat és una
   fila de `recintes`, no una heurística del build. Els àlies del DWG —«E.S. Esso» cap a ESSO—
   són una columna de `unitats`.

### El build no publica un full incoherent

Abans de generar res, `build-data.mjs` comprova que no hi hagi cap fitxa que apunti a una unitat
inexistent, cap unitat amb dues fitxes vigents del mateix volum, cap recinte assignat a una unitat
que no hi és i cap clau citada que no existeixi. Si en troba, escriu què passa i s'atura amb error:
val més un desplegament que falla que una web que menteix.

## Si el build es queixa

Dues coses que val la pena saber abans de perdre-hi estona, totes dues perquè Google no falla
quan hauria de fallar.

**«La pestanya X no té la columna Y».** Quan demanes una pestanya que no existeix, Google no
dona error: **et torna la primera del full**. Per això el build comprova, en llegir cada
pestanya, que hi sigui la seva columna clau. Si les columnes que ensenya l'error són d'una altra
pestanya, o el `FULL` de `scripts/config.mjs` encara apunta al full vell, o la pestanya es diu
d'una altra manera —van totes en minúscula i sense accents.

**Si diu que _totes_ les fitxes apunten a unitats que no existeixen**, el problema no és cap
fitxa: és que la pestanya `unitats` no s'ha llegit bé.

Google serveix els CSV endevinant quines files són capçalera, i quan una columna és del tot buida
—a `unitats` n'hi ha tres: `avis_propi`, `notes` i `substituida_per`— s'equivoca i desplaça els
noms de columna. Per això el build demana
`headers=1`, que li treu l'endevinalla. Si tot i així falla, es pot mirar què arriba:

```bash
node scripts/mira-pestanya.mjs unitats
```

Ha de sortir `id_ua` com a primera capçalera. Si en surten d'altres, o «A, B, C», vol dir que la
primera fila del full no és la de les capçaleres: comprova que no hi hagi cap fila o columna
afegida a sobre o a l'esquerra.

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
surten els noms. Amb ratolí, passar per sobre d'una unitat n'ensenya el nom i clicar-la obre la
fitxa; sense ratolí, el primer toc ensenya el nom i el segon obre la fitxa.

**El dibuix i l'assignació van per separat.** `data/geometria.json` porta els perímetres, un per
recinte i sense dir de qui són. Qui diu de quina unitat és cada recinte és la pestanya `recintes`
del full. Així, corregir una assignació és tocar una cel·la i tornar a desplegar.

### Quan arriba un plànol nou

Demana'l **en GeoJSON**: és obert, porta el sistema de coordenades a dins i qualsevol SIG l'exporta
(el QGIS obre el DWG i el treu sense res més). Si només hi ha DWG, també serveix; cal LibreDWG per
convertir-lo primer:

```bash
dwgread -O JSON -o planol.json Parcelles_UAs.dwg
```

Després, deixa el fitxer a `data/planol-nou.geojson` (o `.json`) del repositori — des del web de
GitHub, arrossegant-lo. El workflow *Plànol nou* el compara amb el full i deixa el resultat a
Actions. També es pot fer a mà:

```bash
pip install pyproj
python scripts/planol-nou.py planol.geojson data/ recintes.csv unitats.csv
```

Cada recinte surt marcat a la columna `canvi`:

- **IGUAL** — hi era i no ha canviat. No el toquis.
- **NOU** — no hi era. Si porta un nom escrit a dins que coincideix amb una unitat, ve amb la
  proposta feta; si no, l'`id_ua` queda buit.
- **CANVIAT** — hi era però ara té una altra forma. Val la pena mirar si segueix sent de qui era.
- **DESAPAREGUT** — ja no és al plànol. Queda `retirat`, no s'esborra.

### La taula de treball: `public/recintes.html`

`R0184` no diu res mirant-lo, i per això el build genera **`public/recintes.html`**, que és una
eina de manteniment i no forma part de la web pública (va amb `noindex` i cap enllaç no hi porta).

Té tres columnes. A l'esquerra, **dues llistes**: la de *recintes* —sense unitat, assignats o
tots— i la d'*unitats* —les que no quadren, les que no tenen cap recinte, o totes—, amb cercador.
Al mig, **el plànol** amb l'ortofoto: taronja el que no té unitat, verd el que sí, i destacat el
que tens triat. A la dreta, **la fitxa**: classificació, superfície, claus, els recintes que té
amb el compte de si sumen, i **el plànol de la fitxa**, que és el que de debò et diu quina forma
té la unitat. Si en té dues, hi ha un botó per volum.

Tot està lligat: cliques una unitat i el plànol hi va i te la pinta sencera; cliques un dels seus
recintes i t'hi acostes; cliques un recinte del plànol i te'n surt la unitat. Al capdavall de la
columna dreta s'hi van acumulant les files `id_recinte,id_ua` per copiar al full.

**El que assignes es desa al navegador** (`localStorage`), o sigui que tancar la pestanya per
error no s'emporta la feina. Això no substitueix el full: el que mana és el full, i el desat
només serveix per no haver de tornar a començar. En tornar a obrir la pàgina després d'un
desplegament, les assignacions que ja siguin al full desapareixen soles del desat.

**Una unitat pot tenir més d'un recinte**, i no és cap raresa: n'hi ha 24, i Molina en té sis. La
relació és de molts recintes a una unitat, i al full això són senzillament unes quantes files amb
el mateix `id_ua`. Per això la pàgina no diu si una unitat «ja té recinte» —que no vol dir res—
sinó **si els que té sumen la superfície que diu la fitxa**: «6 recintes · li falten 7.381 m²».
Quan el recinte que tens obert és justament el que faria quadrar una unitat, la seva fila surt
marcada.

Aquesta comparació és també la manera de trobar els recintes mal repartits. Per exemple R0029,
que fa 103.440 m² i porta escrits dos noms a dins: amb ell, Cabeca passa de 71.670 a 175.111 m²
contra els 174.827 que diu la fitxa, o sigui que és seu, i el nom de «Costes 1» que hi ha a dins
és una etiqueta amb línia de guia que hi ha caigut a sobre.

Enganxa al full **només les files que no diguin IGUAL**, omple l'`id_ua` de les noves i posa-hi
`assignat_per = revisat`. El guió no toca mai una fila revisada, i els identificadors es mantenen
perquè aparella per lloc i superfície, no per ordre.

El sistema de coordenades: el cadastre va en NTF (Paris) / Lambert Sud, `EPSG:27563`. El GeoJSON
surt en graus (`EPSG:4326`), que és el que demana el format, i la geometria del navegador en Web
Mercator (`EPSG:3857`), que és el dels mosaics de fons.

**Una cosa que diu el guió cada vegada:** al DWG d'avui hi ha **nou recintes dibuixats dues
vegades**, un damunt de l'altre. No fan mal, però val la pena dir-ho a qui manté el dibuix.

### Més capes

La pestanya `capes` diu quines capes es dibuixen: nom, fitxer, color i si surt encesa. Afegir-ne
una és deixar el GeoJSON a `data/` i escriure-hi la fila. El DWG ja en porta tres que no publiquem
i que gairebé no pesen —sòl privat en SNU per risc (143 recintes), protecció 15 m (27) i sòl
comunal (3)— i les parcel·les del cadastre (4.432), que són l'única que pesa de debò: 188 KB
contra els 84 KB de totes les unitats juntes.

### El mapa de fons

Es tria amb els botons de dalt a l'esquerra: *Ortofoto* (World Imagery d'Esri), *Mapa*
(OpenStreetMap) o *Cap*. Tots dos són gratuïts i només demanen que se'n digui la procedència, cosa
que la pàgina fa a sota dels botons. Per canviar de proveïdor n'hi ha prou amb tocar l'objecte
`FONS` de `src/index.html`; si algun dia es vol Google Maps, cal una clau de l'API amb facturació
activada i fer servir el seu SDK, perquè les seves condicions no permeten agafar-ne els mosaics
pel seu compte.

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

La **classificació** de cada part surt de la seva fitxa (`Parametres.classificacio`). Si aquella
fila no la diu, es mira la fila de la pestanya `UA` d'aquell volum, si n'hi ha; i si tampoc, el
volum decideix: el VII és, per definició, sòl no urbanitzable. Abans en aquest cas s'heretava la
classificació de la unitat, i una part de sòl no urbanitzable sortia com a urbanitzable (passava a
Boixader i a Envalira de Dalt 3).

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

## La pàgina «Qui regula què»

`src/esquema.html` és una segona pàgina, independent de la consulta per unitats: explica **quin
nivell del pla decideix cada paràmetre**. Hi ha quatre nivells —la fitxa de la unitat, la subzona
(articles 67–80), la zona (61–66) i les normes genèriques del volum II— i la gràcia és que el
nivell concret sovint no dona el valor sinó que hi remet: l'article 67.h envia les alçades a la
fitxa i el 67.i envia la manera de mesurar-les a l'article 30.

La pàgina es filtra per nivell i per text, i cada fila s'obre amb **el text de la norma**. Els
articles de zona i subzona no s'hi mostren tal com surten —hi encabeixen els divuit paràmetres en
un sol apartat inacabable—, sinó partits per lletra a partir de `Claus_parametres`, que és com es
llegeixen de veritat.

El build els incrusta sols: llegeix `src/esquema.html`, en treu els `Article NN` que cita i hi posa
el text de `Normativa_apartats` i els paràmetres de `Claus_parametres`. Afegir una fila nova a la
taula és tocar l'array `FILES` del final del fitxer; si cita un article que abans no hi era, el text
hi apareix tot sol al següent build.

La correspondència entre paràmetre i nivell és lectura de la norma, no un camp del full: si en
canvia alguna, es corregeix a `FILES`.

## Com es fa un canvi

| Cas | Què toques |
|---|---|
| **Unitat nova** | Fila a `unitats` · fila a `documents` · fila a `fitxes` (vigent = SÍ) · el plànol al Drive i el seu id a la fitxa · el recinte a `recintes` quan arribi el plànol · una línia a `canvis` |
| **Modificació (M05…)** | La fitxa d'ara: `vigent = NO` i `vigent_fins_a` · fila nova a `fitxes` · document i plànol nous |
| **Unitat derogada** | A `unitats`, `estat = derogada` · totes les seves fitxes a `vigent = NO` · el recinte a `retirat` |
| **Canvi de clau o d'article** | La fila nova a `claus` o `claus_parametres`; els textos planers tornen a `revisat = NO` |
| **Capa nova al plànol** | El GeoJSON a `data/` i una fila a `capes` |

Sense el pas del recinte, una unitat nova ja funciona: surt al cercador i té fitxa; només no es
pinta al plànol.

## La migració del full vell

`scripts/migra-full.py` munta el full nou a partir del vell. No reescriu cap dada a mà i es pot
tornar a executar tantes vegades com calgui:

```bash
pip install openpyxl
python scripts/migra-full.py poupe_full.json contingut.xlsx data/recintes.csv nou/
```

En surten els 19 CSV i un `POUPE_full_nou.xlsx` per importar a Google Sheets. El que fa, pestanya
per pestanya, és al capdamunt del guió.

Comprovat: generant el `data.json` amb el full vell i amb el nou, les 403 unitats surten idèntiques
tret de dos codis de clau que abans s'escrivien en majúscula («ÉA» contra «éa»), que són soroll de
l'extracció i no afecten res.

## Què queda per fer

- **Cerca per referència cadastral.** La pestanya `Cadastre` del full de dades encara és buida.
- **Revisar els textos planers.** A `valors_public` i `claus_public` la majoria de files encara
  tenen `revisat = NO`: són redaccions fetes llegint la norma, però sense validar una per una.
  Cada frase corregida es propaga a totes les unitats que fan servir aquella clau.

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

- **Plànol interactiu.** Quan hi hagi el DWG de les unitats convertit a GeoJSON, el selector de
  zona i subzona es pot substituir per una tria damunt del mapa. Els identificadors (`id_ua`) ja
  són els que faria servir el mapa, o sigui que no cal tocar res més.
- **Cerca per referència cadastral.** La pestanya `Cadastre` del full de dades encara és buida.
- **Revisar els textos planers.** A `valors_public` i `claus_public` la majoria de files encara
  tenen `revisat = NO`: són redaccions fetes llegint la norma, però sense validar una per una.
  Cada frase corregida es propaga a totes les unitats que fan servir aquella clau.

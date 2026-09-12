/**
 * Llegeix el full de càlcul del POUPE i escriu public/data.json.
 * No té cap dependència: només Node 18 o superior.
 *
 *   node scripts/build-data.mjs
 */
import { writeFile, mkdir, readFile } from 'node:fs/promises';
import { FULL, PESTANYES } from './config.mjs';

const ARREL = new URL('..', import.meta.url).pathname;

/* ------------------------------------------------------------------ CSV */
function parseCSV(text) {
  const files = [];
  let camp = '', fila = [], dins = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (dins) {
      if (c === '"') {
        if (text[i + 1] === '"') { camp += '"'; i++; } else dins = false;
      } else camp += c;
    } else if (c === '"') dins = true;
    else if (c === ',') { fila.push(camp); camp = ''; }
    else if (c === '\n') { fila.push(camp); files.push(fila); fila = []; camp = ''; }
    else if (c !== '\r') camp += c;
  }
  if (camp || fila.length) { fila.push(camp); files.push(fila); }
  return files;
}

function aObjectes(files) {
  if (!files.length) return [];
  const caps = files[0].map(c => (c || '').trim());
  return files.slice(1)
    .map(f => Object.fromEntries(caps.map((c, i) => [c, (f[i] ?? '').trim()])))
    .filter(o => Object.values(o).some(v => v !== ''));
}

// Mode local: si POUPE_CSV apunta a una carpeta, llegeix <carpeta>/<pestanya>.csv
// en comptes d'anar als fulls de càlcul. Serveix per treballar sense connexió.
const LOCAL = process.env.POUPE_CSV || '';

async function pestanya(id, nom) {
  if (LOCAL) {
    const { readFile } = await import('node:fs/promises');
    return comprova(nom, aObjectes(parseCSV(await readFile(`${LOCAL}/${nom}.csv`, 'utf8'))));
  }
  // headers=1 és imprescindible: sense això Google endevina quantes files són
  // capçalera, i quan una columna és del tot buida s'equivoca i desplaça els noms.
  const url = `https://docs.google.com/spreadsheets/d/${id}/gviz/tq?tqx=out:csv&headers=1&sheet=${encodeURIComponent(nom)}`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`No s'ha pogut llegir «${nom}» (${r.status}). El full està compartit amb enllaç?`);
  const t = await r.text();
  if (t.startsWith('<')) throw new Error(`«${nom}» ha tornat HTML: el full no és públic o la pestanya no existeix.`);
  return comprova(nom, aObjectes(parseCSV(t)));
}

// Cada pestanya ha de portar la seva columna clau. Comprovar-ho en llegir-la és
// important per una raó concreta: quan demanes a Google una pestanya que no existeix,
// no et dona error — et torna la primera del full. Sense aquesta comprovació, el build
// es passa mitja hora treballant amb les dades equivocades i falla molt més enllà.
const CLAU = {
  documents: 'id_document', fitxes: 'id_fitxa', unitats: 'id_ua', recintes: 'id_recinte',
  articles: 'article', apartats: 'id_apartat', claus: 'clau', claus_parametres: 'id_valor',
  proteccions: 'nom', config: 'clau', textos: 'id_text', blocs: 'id_bloc',
  parametres: 'parametre_bd', avisos: 'id_avis', glossari: 'terme', capes: 'id_capa',
};

function comprova(nom, files) {
  const clau = CLAU[nom];
  if (!clau || !files.length) return files;
  const cols = Object.keys(files[0]);
  if (cols.includes(clau)) return files;
  throw new Error(
    `La pestanya «${nom}» no té la columna «${clau}».\n`
    + `  Columnes llegides: ${cols.join(', ')}\n\n`
    + `  Quan es demana una pestanya que no existeix, Google no dona error: torna la\n`
    + `  primera del full. Si les columnes de sobre són d'una altra pestanya, el més\n`
    + `  probable és que «${nom}» no hi sigui, i això vol dir una d'aquestes dues coses:\n\n`
    + `    · el FULL de scripts/config.mjs encara apunta al full vell\n`
    + `    · la pestanya es diu d'una altra manera (van en minúscula i sense accents)\n\n`
    + `  Per veure què arriba: node scripts/mira-pestanya.mjs ${nom}`);
}

async function llegeixFull(id, noms) {
  const out = {};
  for (const n of noms) { out[n] = await pestanya(id, n); process.stdout.write(`  ${n}: ${out[n].length}\n`); }
  return out;
}

/* -------------------------------------------------------------- utilitats */
const NUM = '(\\d+(?:[.,]\\d+)?)';
const CLASSIF = { SUC: 'sòl urbà consolidat', SUCc: 'sòl urbà consolidat', SUNC: 'sòl urbà no consolidat',
                  SUBLE: 'sòl urbanitzable', SNU: 'sòl no urbanitzable', SNUBLE: 'sòl no urbanitzable' };

const normClau = c => {
  c = (c || '').trim();
  if (!c) return '';
  const m = c.match(/^(\d+|Z[A-Za-z]|[A-Za-z]{1,3})([A-Za-z])?$/);
  if (!m) return c;
  return (m[1] || '').toUpperCase() + (m[2] ? m[2].toUpperCase() : '');
};

function parseClaus(camp) {
  const out = [], vistos = new Set();
  for (const tros of (camp || '').split(/[;,]\s*(?![^()]*\))/)) {
    const m = tros.match(/\(Clau\s+([^)]+)\)/);
    if (!m) continue;
    const brut = m[1].trim();
    const nom = tros.slice(0, m.index).trim();
    let codis;
    if (brut.includes('/')) {
      const arrel = (brut.match(/^(\d+)/) || [])[1] || '';
      codis = brut.split('/').map(x => {
        x = x.trim();
        return /^\d/.test(x) ? normClau(x) : arrel + x.toUpperCase();
      });
    } else codis = [normClau(brut)];
    for (const c of codis) {
      if (c && !vistos.has(c)) { vistos.add(c); out.push({ c, n: nom || c }); }
    }
  }
  return out;
}

const triplet = seg => [
  (seg.match(new RegExp('ARPFM\\)\\s*de l[’\']edificació és de\\s*' + NUM)) || [])[1] || null,
  (seg.match(new RegExp('ARM\\)\\s*de l[’\']edificació fins a carener és de\\s*' + NUM)) || [])[1] || null,
  (seg.match(new RegExp('AM\\)\\s*de l[’\']edifici de\\s*' + NUM)) || [])[1] || null,
];

function alcades(ordenacio, zones) {
  if (!ordenacio) return [];
  const parts = ordenacio.split(/En\s+Zona\s+Urban[a]?\s+/);
  let out;
  if (parts.length > 1) {
    out = parts.slice(1).map(seg => {
      const l = (seg[0] || '').toUpperCase();
      const z = zones.find(x => x.c.endsWith(l));
      return { z: `Zona Urbana ${l}`, c: z ? z.c : '', t: triplet(seg) };
    });
  } else {
    const z = zones[0];
    out = [{ z: z ? z.n : '', c: z ? z.c : '', t: triplet(ordenacio) }];
  }
  return out.filter(o => o.t.some(Boolean));
}

const llista = xs => {
  xs = xs.filter(Boolean);
  return xs.length <= 1 ? (xs[0] || '') : xs.slice(0, -1).join(', ') + ' i ' + xs[xs.length - 1];
};

/* ------------------------------------------------------------------ build */
if (!LOCAL && /^POSA_AQUI/.test(FULL))
  throw new Error("Falta l'identificador del full a scripts/config.mjs.");
console.log('Llegint les pestanyes de la base de dades…');
const F = await llegeixFull(FULL, PESTANYES.bd);
console.log('Llegint les pestanyes de contingut…');
const C = await llegeixFull(FULL, PESTANYES.contingut);

const cfg = Object.fromEntries(C.config.map(r => [r.clau, r.valor]));
const T = Object.fromEntries(C.textos.map(r => [r.id_text, r.text_ca]));
const fmt = (id, vars) => Object.entries(vars)
  .reduce((s, [k, v]) => s.split('{' + k + '}').join(String(v)), T[id] || '');

const blocs = C.blocs.filter(b => b.visible === 'SÍ')
  .sort((a, b) => Number(a.ordre) - Number(b.ordre))
  .map(b => ({ id: b.id_bloc, t: b.titol_public, s: b.subtitol, o: Number(b.ordre) }));

const params = {};
for (const p of C.parametres)
  if (p.visible === 'SÍ' && p.id_bloc)
    params[p.parametre_bd] = { b: p.id_bloc, o: Number(p.ordre), et: p.etiqueta_publica, aj: p.ajuda_curta };

const claus = {};
const variants = {};          // clau mare -> règims alternatius (la subzona 11: 11A i 11B)
for (const c of F.claus) {
  if (c.visible !== 'SÍ') continue;
  const codi = String(c.clau);
  claus[codi] = { n: c.nom_public || c.denominacio_oficial, f: c.frase_planera,
                  a: c.article, t: c.tipus, co: c.coef_edificabilitat || '' };
  const mare = String(c.clau_mare || '').trim();
  if (mare) (variants[mare] ||= []).push(codi);
}

const valors = {};
for (const v of F.claus_parametres) {
  if (v.visible !== 'SÍ' || !params[v.parametre_bd]) continue;
  (valors[String(v.clau)] ||= []).push({ p: v.parametre_bd, pl: v.text_planer, no: v.valor_original, a: v.article });
}

const arts = {};
for (const a of F.articles) arts[(a.article || '').trim()] = { t: a.titol, d: a.document, u: a.url || '' };

const avisos = Object.fromEntries(C.avisos.filter(a => a.visible === 'SÍ')
  .map(a => [a.id_avis, { to: a.to, x: a.text }]));

const fitxes = {};
for (const f of F.fitxes) if (f.id_ua) (fitxes[f.id_ua] ||= []).push(f);
const prot = {};
for (const r of F.proteccions) if (r.id_ua) (prot[r.id_ua] ||= []).push(r);

// La taula de recintes viu al repositori, al costat de la geometria: és una taula que
// manté un guió i que s'edita amb public/recintes.html, no a mà en un full de càlcul.
// Cada canvi hi deixa un commit, que és el millor històric que podíem tenir.
let RECINTES = [];
try {
  RECINTES = aObjectes(parseCSV(await readFile(ARREL + 'data/recintes.csv', 'utf8')));
} catch { console.log('Sense data/recintes.csv: la web sortirà sense plànol.'); }

// Un recinte pot ser de més d'una unitat: al DWG hi ha dibuixos que n'abracen dues.
// Per això id_ua és una llista, amb els identificadors separats per «;».
const uesDe = r => String(r.id_ua || '').split(';').map(x => x.trim()).filter(Boolean);

/* --------- comprovacions: val més un desplegament que falla que una web que menteix */
const ids = new Set(F.unitats.map(u => u.id_ua));
const docs = new Set(F.documents.map(d => d.id_document));
const problemes = [];
for (const f of F.fitxes) {
  // una fitxa sense unitat només s'admet si és un document normatiu: un volum sencer
  if (!f.id_ua) {
    if (f.tipus_fitxa !== 'document normatiu')
      problemes.push(`la fitxa ${f.id_fitxa} no diu de quina unitat és`);
  } else if (!ids.has(f.id_ua)) {
    problemes.push(`la fitxa ${f.id_fitxa} apunta a la unitat ${f.id_ua}, que no existeix`);
  }
  if (f.id_document && !docs.has(f.id_document)) problemes.push(`la fitxa ${f.id_fitxa} apunta al document ${f.id_document}, que no existeix`);
}
const dobles = {};
for (const f of F.fitxes) if (f.vigent === 'SÍ') {
  const k = f.id_ua + '|' + f.volum;
  if (dobles[k]) problemes.push(`${f.id_ua} té dues fitxes vigents del volum ${f.volum}: ${dobles[k]} i ${f.id_fitxa}`);
  dobles[k] = f.id_fitxa;
}
for (const r of RECINTES) {
  for (const u of String(r.id_ua || '').split(';').map(x => x.trim()).filter(Boolean))
    if (!ids.has(u))
      problemes.push(`el recinte ${r.id_recinte} està assignat a ${u}, que no existeix`);
}
for (const v of F.claus_parametres)
  if (v.visible === 'SÍ' && v.clau && !claus[v.clau])
    problemes.push(`claus_parametres cita la clau ${v.clau}, que no és a la pestanya claus`);
if (problemes.length) {
  console.error('\nEl full no és coherent i no es pot publicar:');
  // si falla gairebé tot, el problema no és fila per fila: és la pestanya sencera
  const orfes = problemes.filter(p => p.includes('que no existeix')).length;
  if (orfes > F.fitxes.length / 2) {
    console.error(`  · ${orfes} fitxes apunten a unitats que no existeixen: pràcticament totes.`);
    console.error(`    La pestanya «unitats» s'ha llegit amb ${F.unitats.length} files i les columnes`);
    console.error(`    ${Object.keys(F.unitats[0] || {}).join(', ') || '(cap)'}.`);
    console.error('    Comprova que la primera fila del full és la de les capçaleres i que no hi ha');
    console.error('    cap fila ni columna afegida a sobre o a l\'esquerra.');
  } else {
    for (const p of [...new Set(problemes)].slice(0, 30)) console.error('  · ' + p);
    if (problemes.length > 30) console.error(`  · …i ${problemes.length - 30} més`);
  }
  process.exit(1);
}
console.log('\nEl full és coherent.');

// Una unitat pot tenir més d'una fitxa vigent: una per volum del pla. Vol dir que la
// unitat té dues parts amb classificacions diferents —la urbana i la de sòl no
// urbanitzable—, cadascuna amb la seva superfície, els seus paràmetres i el seu plànol.
// Cada part és un registre sencer; la pàgina en mostra una i deixa triar.
const VOLUM = { III: "Vall d'Encamp", IV: 'Els Cortals', V: 'Pas de la Casa',
                VI: 'Sòl urbanitzable', VII: 'Sòl no urbanitzable' };

const UA = [];
for (const u of F.unitats) {
  const idu = (u.id_ua || '').trim();
  if (!idu || !(u.nom_oficial || '').trim()) continue;
  if (u.visible === 'NO' || u.estat === 'derogada') continue;
  const fs = fitxes[idu] || [];
  const vig = fs.filter(f => f.vigent === 'SÍ');
  const perVolum = new Map();
  for (const f of (vig.length ? vig : fs.slice(0, 1)))
    if (!perVolum.has(f.volum)) perVolum.set(f.volum, f);

  const rec = { id: idu, n: u.nom_public || u.nom_oficial, tf: '', parts: [], fx: [] };

  const vols = [...perVolum.keys()].sort((x, y) =>
    (x === 'VII' ? 1 : 0) - (y === 'VII' ? 1 : 0) || String(x).localeCompare(String(y)));

  for (const vol of vols) {
    const p = perVolum.get(vol);                 // la fitxa ja porta els paràmetres
    const z = parseClaus(p.zones), sz = parseClaus(p.subzones);

    const part = {
      vol, idf: p.id_fitxa, np: VOLUM[vol] || ('Volum ' + vol),
      cls: p.classificacio, tf: p.tipus_fitxa, sup: p.superficie_m2 || '',
      cob: p.cobertura || '', edif: p.edificabilitat_max_m2 || '',
      z, sz, clau: [z.map(x => x.c).join('·'), sz.map(x => x.c).join('·')].filter(Boolean).join(' / '),
      raw: {}, av: [], pr: [],
    };
    if (p.ordenacio) part.raw.o = p.ordenacio;
    if (p.usos) part.raw.u = p.usos;
    if (p.gestio) part.raw.g = p.gestio;

    // resum
    if (u.resum_que_es) {
      part.res = [u.resum_que_es, u.resum_que_shi_pot_fer, u.resum_com_es_desenvolupa];
    } else {
      const cl = CLASSIF[part.cls] || part.cls || 'sòl sense classificar';
      const f1 = part.sup ? fmt('resum_1', { superficie: part.sup, classificacio: cl })
                          : fmt('resum_1_sense_sup', { classificacio: cl });
      const nz = llista(z.map(x => (claus[x.c] || {}).n || x.n));
      const ns = llista(sz.map(x => (claus[x.c] || {}).n || x.n));
      let f2;
      if (z.length && sz.length)
        f2 = fmt(z.length + sz.length > 2 ? 'resum_zones_n' : 'resum_zones_1', { zones: nz, subzones: ns });
      else if (z.length || sz.length) {
        const un = nz || ns;
        f2 = (z.length + sz.length === 1)
          ? `Tota la unitat és ${un}.`
          : `Hi conviuen ${un}: el que pots fer depèn d'on és exactament la teva parcel·la.`;
      } else f2 = T.resum_zones_cap || '';
      const g = (p.gestio || '').toLowerCase();
      const f3 = g.includes('pla parcial') ? T.gestio_pla_parcial : (g.includes('directa') ? T.gestio_directa : '');
      part.res = [f1, f2, f3];
    }

    // avisos
    const idsAv = [];
    const mapa2 = { SUBLE: 'AV1', SUNC: 'AV2', SNUBLE: 'AV3', SNU: 'AV3' };
    if (mapa2[part.cls]) idsAv.push(mapa2[part.cls]);
    if (part.tf === 'àrea diferenciada') idsAv.push('AV4');
    if (part.tf === 'UA definició volumètrica') idsAv.push('AV5');
    if (prot[idu]) idsAv.push('AV6');
    if (fs.some(f => f.modificacio !== 'M00')) idsAv.push('AV7');
    if ((part.cob || '').includes('sense aprofitament privat')) idsAv.push('AV8');
    part.av = idsAv.filter(i => avisos[i]).map(i => ({ ...avisos[i] }));
    if (u.avis_propi) part.av.push({ to: 'atencio', x: u.avis_propi });

    // punts propis de la fitxa
    for (const a of alcades(p.ordenacio, z)) {
      const [arpfm, arm, am] = a.t;
      let frase = '';
      if (arpfm && arm) frase = fmt('alcada_zona', { zona: a.z, arpfm, arm });
      else if (arm) frase = a.z ? `A la ${a.z}: el carener pot arribar a ${arm} m.` : `El carener pot arribar a ${arm} m.`;
      else if (arpfm) frase = a.z ? `A la ${a.z}: la façana pot arribar a ${arpfm} m.` : `La façana pot arribar a ${arpfm} m.`;
      if (am) frase += ' ' + fmt('alcada_am', { am });
      part.pr.push({ b: 'B4', o: 5, et: 'Alçada màxima', aj: T.avis_alcades || '',
                     pl: frase.trim(), nk: 'o', c: a.c, niv: 'zona', src: 'fitxa' });
    }
    if (!z.length && p.alcades) {
      const m = p.alcades.match(new RegExp('carener:\\s*' + NUM));
      if (m) part.pr.push({ b: 'B4', o: 5, et: 'Alçada màxima', aj: T.avis_alcades || '',
                            pl: `L'edifici pot arribar a ${m[1]} m fins al carener.`, nk: 'o',
                            c: '', niv: 'fitxa', src: 'fitxa' });
    }
    if (part.edif) part.pr.push({ b: 'B3', o: 5, et: 'Sostre màxim de la unitat',
                                  aj: "Aquí el sostre no surt d'un coeficient: la fitxa l'assigna directament.",
                                  pl: fmt('sostre_fitxa', { edificabilitat: part.edif }), nk: 'o',
                                  c: '', niv: 'fitxa', src: 'fitxa' });
    if (p.usos) {
      const exc = p.usos.match(/excepte\s+([\s\S]*?)\.?\s*$/);
      part.pr.push({ b: 'B2', o: 5, et: "Excepcions d'aquesta unitat",
                     aj: 'Usos que la subzona permet però la fitxa exclou.',
                     pl: exc ? fmt('usos_excepcio', { excepcio: exc[1].trim() }) : p.usos,
                     nk: 'u', c: '', niv: 'fitxa', src: 'fitxa' });
    }
    if (p.gestio) {
      const g = p.gestio.toLowerCase();
      const base = g.includes('pla parcial') ? T.gestio_pla_parcial
                 : (g.includes('directa') ? T.gestio_directa : p.gestio);
      part.pr.push({ b: 'B7', o: 10, et: 'Com es desenvolupa', aj: 'Què cal fer abans de poder edificar.',
                     pl: (base + ' ' + (T.gestio_coda || '')).trim(), nk: 'g', c: '', niv: 'fitxa', src: 'fitxa' });
    }
    for (const pr2 of (prot[idu] || []))
      part.pr.push({ b: 'B8', o: 10, et: pr2.nom, aj: `${pr2.categoria} — ${pr2.tipus}`,
                     pl: pr2.obligacio, c: '', niv: 'fitxa', src: 'prot', art: pr2.article });

    rec.parts.push(part);
  }

  if (!rec.parts.length) continue;
  rec.tf = rec.parts[0].tf;

  // fitxes: totes, amb el volum a què pertanyen
  const doc = Object.fromEntries(F.documents.map(d => [d.id_document, d]));
  for (const f of [...fs].sort((a, b) => (a.vigent === 'SÍ' ? 0 : 1) - (b.vigent === 'SÍ' ? 0 : 1)
                                      || String(a.volum).localeCompare(String(b.volum))
                                      || String(a.modificacio).localeCompare(String(b.modificacio)))) {
    const d = doc[f.id_document] || {};
    rec.fx.push({ idf: f.id_fitxa, m: f.modificacio, v: f.volum, vig: f.vigent === 'SÍ',
                  fase: d.fase_aprovacio, b: `BOPA núm. ${d.bopa_num}, ${d.bopa_data}`,
                  pg: d.bopa_pagina, pdf: f.pdf_drive_id, img: f.planol_drive_id || '' });
  }
  UA.push(rec);
}

UA.sort((a, b) => a.n.toLowerCase().localeCompare(b.n.toLowerCase(), 'ca'));

/* --------- els textos repetits van a un magatzem comú, per pesar menys */
const pool = [], pidx = new Map();
const intern = t => {
  // Hi ha blocs (avisos, propietats de clau) que es comparteixen per referència entre
  // unitats: si ja s'han internat, tornen l'índex i no s'han de tornar a internar.
  if (typeof t === 'number') return t;
  if (!t) return null;
  if (!pidx.has(t)) { pidx.set(t, pool.length); pool.push(t); }
  return pidx.get(t);
};
for (const r of UA) {
  r.tf = intern(r.tf);
  for (const pt of r.parts) {
    pt.raw = Object.fromEntries(Object.entries(pt.raw).map(([k, v]) => [k, intern(v)]));
    pt.res = (pt.res || []).map(intern);
    for (const a of pt.av) a.x = intern(a.x);
    for (const it of pt.pr) for (const k of ['et', 'aj', 'pl']) if (k in it) it[k] = intern(it[k]);
    for (const k of ['cob', 'tf', 'cls', 'np']) pt[k] = intern(pt[k]);
  }
  for (const f of r.fx) { f.fase = intern(f.fase); f.b = intern(f.b); }
}

// Geometria del plànol. El dibuix és data/geometria.json, una entrada per recinte i
// res més; qui diu de quina unitat és cada recinte és la pestanya «recintes» del full.
// Així, reassignar-ne un és tocar una cel·la i tornar a desplegar: no cal refer res.
let mapa = null;
try {
  const geo = JSON.parse(await readFile(ARREL + 'data/geometria.json', 'utf8'));
  const publicades = new Set(UA.map(u => u.id));
  const ua = {};
  let orfes = 0, compartits = 0;
  for (const r of RECINTES) {
    if (r.estat === 'retirat' || r.estat === 'duplicat') continue;
    const ues = uesDe(r);
    if (!ues.length) { orfes++; continue; }
    if (ues.length > 1) compartits++;
    const anell = geo.r[r.id_recinte];
    if (!anell) continue;
    for (const u of ues) if (publicades.has(u)) (ua[u] ||= []).push(anell);
  }
  mapa = { o: geo.o, ua, n: Object.keys(ua).length };
  console.log(`Plànol: ${mapa.n} unitats dibuixades amb ${RECINTES.length} recintes`
    + (compartits ? ` · ${compartits} recintes compartits per més d'una unitat` : '')
    + (orfes ? ` · ${orfes} sense unitat` : ''));
} catch { console.log('\nSense data/geometria.json: la web sortirà sense plànol.'); }

/* ------------------------------------------------------- capes del plànol

   Cada fila de «capes» és un GeoJSON que viu a data/ i que es dibuixa al plànol
   de la portada amb la seva casella al selector. La geometria es guarda igual
   que la de les unitats —Web Mercator, sense l'origen i amb deltes al metre—
   perquè el navegador no hagi d'aprendre dos formats.

   El GeoJSON ha de venir en graus (EPSG:4326), que és el que diu l'estàndard i
   el que treu qualsevol SIG quan li demanes «GeoJSON». Si ve en coordenades del
   cadastre, el build s'atura i t'ho diu.                                        */
const RADI = 6378137;
const aMercator = (lon, lat) => [
  RADI * lon * Math.PI / 180,
  RADI * Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360)),
];

// Douglas–Peucker en la forma estable: a 2 m no es nota i estalvia molt de pes
function simplifica(p, tol) {
  if (p.length < 3) return p;
  const d2 = (q, a, b) => {
    const dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy;
    let t = l2 ? ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / l2 : 0;
    t = Math.max(0, Math.min(1, t));
    const ex = a[0] + t * dx - q[0], ey = a[1] + t * dy - q[1];
    return ex * ex + ey * ey;
  };
  const guarda = new Uint8Array(p.length);
  guarda[0] = guarda[p.length - 1] = 1;
  const pila = [[0, p.length - 1]], t2 = tol * tol;
  while (pila.length) {
    const [i, j] = pila.pop();
    let pitjor = -1, k = -1;
    for (let m = i + 1; m < j; m++) {
      const d = d2(p[m], p[i], p[j]);
      if (d > pitjor) { pitjor = d; k = m; }
    }
    if (pitjor > t2 && k > 0) { guarda[k] = 1; pila.push([i, k], [k, j]); }
  }
  return p.filter((_, i) => guarda[i]);
}

function deltes(p, o) {
  const d = [];
  let x = null, y = null;
  for (const q of p) {
    const X = Math.round(q[0] - o[0]), Y = Math.round(q[1] - o[1]);
    if (x === null) d.push(X, Y);
    else if (X === x && Y === y) continue;        // el mateix punt dues vegades
    else d.push(X - x, Y - y);
    x = X; y = Y;
  }
  return d;
}

function formesDeGeoJSON(g, o, nomCapa) {
  const crs = ((g.crs || {}).properties || {}).name || '';
  if (crs && !/4326|CRS84/i.test(crs))
    throw new Error(`ve en ${crs}; exporta-la en graus (EPSG:4326)`);
  const etiqueta = pr => String(pr.nom || pr.NOM || pr.name || pr.nom_public
    || pr.etiqueta || pr.descripcio || '').trim();
  const dades = pr => {
    const d = {};
    for (const [k, v] of Object.entries(pr || {})) {
      if (v == null || v === '' || typeof v === 'object') continue;
      if (Object.keys(d).length >= 8) break;
      d[k] = String(v).slice(0, 140);
    }
    return d;
  };
  const trets = g.features || (g.type === 'Feature' ? [g] : []);
  const out = [];
  for (const f of trets) {
    const geo = f.geometry || {}, pr = f.properties || {}, t = geo.type;
    let grups = [];
    if (t === 'Polygon') grups = [['p', geo.coordinates]];
    else if (t === 'MultiPolygon') grups = geo.coordinates.map(x => ['p', x]);
    else if (t === 'LineString') grups = [['l', [geo.coordinates]]];
    else if (t === 'MultiLineString') grups = [['l', geo.coordinates]];
    else if (t === 'Point') grups = [['x', [[geo.coordinates]]]];
    else if (t === 'MultiPoint') grups = geo.coordinates.map(c => ['x', [[c]]]);
    else continue;
    for (const [tipus, anells] of grups) {
      const a = [];
      for (const an of anells) {
        for (const c of an) if (Math.abs(c[0]) > 180 || Math.abs(c[1]) > 90)
          throw new Error('les coordenades no són graus; exporta-la en EPSG:4326');
        let p = an.map(c => aMercator(c[0], c[1]));
        if (tipus !== 'x') p = simplifica(p, 2);
        if (p.length >= (tipus === 'x' ? 1 : 2)) a.push(deltes(p, o));
      }
      if (a.length) out.push({ t: tipus, n: etiqueta(pr), d: dades(pr), a });
    }
  }
  if (!out.length) throw new Error('no s\u2019hi ha trobat cap forma dibuixable');
  return out;
}

let capes = [];
const capesMal = [];
if (mapa) {
  for (const c of (C.capes || [])) {
    if (c.visible !== 'SÍ' || c.id_capa === 'unitats') continue;
    if (!c.fitxer) { capesMal.push(`la capa «${c.id_capa}» no diu quin fitxer és`); continue; }
    try {
      const g = JSON.parse(await readFile(ARREL + c.fitxer, 'utf8'));
      const f = formesDeGeoJSON(g, mapa.o, c.id_capa);
      const color = /^#[0-9a-f]{6}$/i.test((c.color || '').trim()) ? c.color.trim() : '#8C4526';
      capes.push({ i: c.id_capa, n: c.nom_public || c.id_capa, c: color,
                   o: Number(c.ordre) || 50, p: c.per_defecte === 'SÍ',
                   k: c.clicable !== 'NO', f: c.font || '', g: f });
      console.log(`  capa «${c.nom_public || c.id_capa}»: ${f.length} formes`
        + ` · ${Math.round(JSON.stringify(f).length / 1024)} KB`);
    } catch (e) {
      capesMal.push(`la capa «${c.id_capa}» (${c.fitxer}): ${e.message}`);
    }
  }
  capes.sort((a, b) => a.o - b.o);
  if (capes.length) console.log(`Capes: ${capes.length} damunt del plànol`);
}
if (capesMal.length) {
  console.error('\nNo es publica: hi ha capes que no es poden dibuixar.\n');
  for (const m of capesMal) console.error('  · ' + m);
  console.error('\nMira la pestanya «capes» del full: la columna «fitxer» ha de ser el camí'
    + '\ndins del repositori (data/el-que-sigui.geojson) i el fitxer hi ha de ser.'
    + '\nPer treure una capa sense esborrar-la, posa-li «visible» a NO.\n');
  process.exit(1);
}

const data = { pool, cfg, T, blocs, params, claus, variants, valors, arts, ua: UA, mapa, capes,
               glossari: C.glossari.filter(g => g.visible === 'SÍ')
                 .map(g => ({ t: g.terme, d: g.definicio_planera })),
               generat: new Date().toISOString() };

await mkdir(ARREL + 'public', { recursive: true });
await writeFile(ARREL + 'public/data.json', JSON.stringify(data));

// src/*.html són només el cos de la pàgina; aquí els emboliquem en un document complet.
// Les primeres línies (<title>, <link> de tipografies, <style>) van al <head>.
const embolcalla = (brut, desc) => {
  const tall = brut.indexOf('</style>');
  const cap = tall < 0 ? '' : brut.slice(0, tall + 8);
  const cos = tall < 0 ? brut : brut.slice(tall + 8).replace(/^\n/, '');
  return `<!doctype html>
<html lang="ca">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="${desc}">
<meta name="robots" content="index,follow">
<style>*{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>
${cap}
</head>
<body>
${cos}
</body>
</html>
`;
};

const doc = embolcalla(await readFile(ARREL + 'src/index.html', 'utf8'),
  "Consulta del POUPE d'Encamp per unitat d'actuació, en llenguatge planer i amb la font de cada punt. Web independent.");
await writeFile(ARREL + 'public/index.html', doc);
/* --------- la pàgina de l'esquema: qui regula què, amb el text dels articles
   El cos és src/esquema.html; d'allà se'n treuen els articles que cita i s'hi
   incrusta el text que en guarda la pestanya Normativa_apartats. */
const brutEsq = await readFile(ARREL + 'src/esquema.html', 'utf8');
const citats = new Set((brutEsq.match(/Article \d+/g) || []));
const artsEsq = {};
for (const r of F.apartats) {
  if (!citats.has(r.article)) continue;
  (artsEsq[r.article] ||= { t: (arts[r.article] || {}).t || '',
                           f: (F.articles.find(a => a.article === r.article) || {}).bopa || '',
                           ap: [] })
    .ap.push([r.apartat, (r.text || '').trim()]);
}
// els articles de zona i subzona porten tots els paràmetres en un sol apartat inacabable;
// la pestanya Claus_parametres els té partits per lletra, que és com es llegeixen
const clausArt = {};
for (const r of F.claus_parametres) {
  if (!citats.has(r.article)) continue;
  (clausArt[r.article] ||= []).push({
    c: r.clau, l: r.lletra, p: r.parametre, v: r.valor_original,
    n: r.valor_numeric, u: r.unitat, r: r.remet_a });
}
await writeFile(ARREL + 'public/esquema.html',
  embolcalla(brutEsq.replace('__CLAUS__', () => JSON.stringify(clausArt).replace(/</g, '\\u003c'))
    .replace('__ARTICLES__',
    () => JSON.stringify(artsEsq).replace(/</g, '\\u003c')),
    "Quin nivell del POUPE d'Encamp decideix cada paràmetre: la fitxa, la subzona, la zona o les normes genèriques."));
console.log(`Esquema: ${Object.keys(artsEsq).length} articles incrustats a public/esquema.html`);

/* --------- la pàgina per assignar recintes a unitats
   Va a part de la web pública: és una eina de manteniment. Hi porta la geometria, la
   taula de recintes i els noms de les unitats, i prou. */
try {
  const geo = JSON.parse(await readFile(ARREL + 'data/geometria.json', 'utf8'));
  const nom = Object.fromEntries(F.unitats.map(u => [u.id_ua, u.nom_public || u.nom_oficial]));
  const dadesRec = {
    o: geo.o,
    r: RECINTES.filter(r => geo.r[r.id_recinte]
                        && r.estat !== 'retirat' && r.estat !== 'duplicat').map(r => ({
      i: r.id_recinte, g: geo.r[r.id_recinte], u: uesDe(r),
      c: (r.capa_dwg || '').replace('01 ', '').replace('UA ', '').trim(),
      s: r.superficie_dwg, n: r.nom_dwg, a: r.assignat_per })),
    // la superfície que diu la fitxa: és el que permet veure si a una unitat de
    // diverses peces encara li'n falta alguna
    u: F.unitats.filter(u => u.estat !== 'derogada').map(u => {
      const fs = (fitxes[u.id_ua] || []).filter(f => f.vigent === 'SÍ');
      const urb = fs.filter(f => f.volum !== 'VII');
      const p = urb[0] || fs[0] || {};
      return {
        i: u.id_ua, n: nom[u.id_ua],
        s: urb.reduce((t, f) => t + (Number(String(f.superficie_m2).replace(/\./g, '').replace(',', '.')) || 0), 0),
        c: p.classificacio || '', k: [p.zones, p.subzones].filter(Boolean).join(' / '),
        t: p.tipus_fitxa || '', v: p.volum || '',
        // les fitxes vigents, per ensenyar-ne el plànol
        f: fs.map(f => ({ id: f.id_fitxa, v: f.volum, s: f.superficie_m2,
                          c: f.classificacio, g: f.gestio || '' })),
      };
    }),
  };
  // les etiquetes del plànol: el nom, allà on el delineant el va escriure
  try {
    dadesRec.e = JSON.parse(await readFile(ARREL + 'data/etiquetes.json', 'utf8'));
  } catch { dadesRec.e = {}; }
  // la taula sencera i les seves capçaleres: la pàgina ha de poder reescriure el CSV
  dadesRec.csv = { cols: Object.keys(RECINTES[0] || {}), files: RECINTES };
  const brutRec = await readFile(ARREL + 'src/recintes.html', 'utf8');
  await writeFile(ARREL + 'public/recintes.html',
    embolcalla(brutRec.replace('__RECINTES__',
      () => JSON.stringify(dadesRec).replace(/</g, '\\u003c')),
      'Eina interna per assignar els recintes del plànol a les unitats.')
      .replace('<meta name="robots" content="index,follow">', '<meta name="robots" content="noindex">'));
  const falten = dadesRec.r.filter(r => !r.u.length).length;
  console.log(`Recintes: ${dadesRec.r.length} a public/recintes.html`
    + (falten ? ` · ${falten} encara sense unitat` : ' · tots assignats'));
} catch (e) { console.log('Sense data/geometria.json: no es genera la pàgina de recintes.'); }

console.log(`\nFet: ${UA.length} unitats · ${Math.round(JSON.stringify(data).length / 1024)} KB a public/data.json`);

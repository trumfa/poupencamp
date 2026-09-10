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
    return aObjectes(parseCSV(await readFile(`${LOCAL}/${nom}.csv`, 'utf8')));
  }
  const url = `https://docs.google.com/spreadsheets/d/${id}/gviz/tq?tqx=out:csv&sheet=${encodeURIComponent(nom)}`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`No s'ha pogut llegir «${nom}» (${r.status}). El full està compartit amb enllaç?`);
  const t = await r.text();
  if (t.startsWith('<')) throw new Error(`«${nom}» ha tornat HTML: el full no és públic o la pestanya no existeix.`);
  return aObjectes(parseCSV(t));
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
const T = Object.fromEntries(C.textos_web.map(r => [r.id_text, r.text_ca]));
const fmt = (id, vars) => Object.entries(vars)
  .reduce((s, [k, v]) => s.split('{' + k + '}').join(String(v)), T[id] || '');

const blocs = C.blocs.filter(b => b.visible === 'SÍ')
  .sort((a, b) => Number(a.ordre) - Number(b.ordre))
  .map(b => ({ id: b.id_bloc, t: b.titol_public, s: b.subtitol, o: Number(b.ordre) }));

const params = {};
for (const p of C.parametres_public)
  if (p.visible === 'SÍ' && p.id_bloc)
    params[p.parametre_bd] = { b: p.id_bloc, o: Number(p.ordre), et: p.etiqueta_publica, aj: p.ajuda_curta };

const claus = {};
const variants = {};          // clau mare -> règims alternatius (la subzona 11: 11A i 11B)
for (const c of C.claus_public) {
  if (c.visible !== 'SÍ') continue;
  const codi = String(c.clau);
  claus[codi] = { n: c.nom_public || c.denominacio_oficial, f: c.frase_planera,
                  a: c.article, t: c.tipus, co: c.coef_edificabilitat || '' };
  const mare = String(c.clau_mare || '').trim();
  if (mare) (variants[mare] ||= []).push(codi);
}

const valors = {};
for (const v of C.valors_public) {
  if (v.visible !== 'SÍ' || !params[v.parametre_bd]) continue;
  (valors[String(v.clau)] ||= []).push({ p: v.parametre_bd, pl: v.text_planer, no: v.valor_original, a: v.article });
}

const arts = {};
for (const a of F.Normativa) arts[(a.article || '').trim()] = { t: a.titol, d: a.font, u: a.url || '' };

const avisos = Object.fromEntries(C.avisos.filter(a => a.visible === 'SÍ')
  .map(a => [a.id_avis, { to: a.to, x: a.text }]));
const overrides = Object.fromEntries(C.ua_public.map(u => [u.id_ua, u]));

const pf = Object.fromEntries(F.Parametres.map(r => [r.id_fitxa, r]));
const fitxes = {};
for (const f of F.Fitxes) (fitxes[f.id_ua] ||= []).push(f);
const img = Object.fromEntries(F.Planols.filter(r => r.drive_id_imatge).map(r => [r.id_fitxa, r.drive_id_imatge]));
const prot = {};
for (const r of F.Proteccions) if (r.id_ua) (prot[r.id_ua] ||= []).push(r);

// Una unitat pot tenir més d'una fitxa vigent: una per volum del pla. Passa a 91 de les
// 405, i vol dir que la unitat té dues parts amb classificacions diferents —la urbana i
// la de sòl no urbanitzable—, cadascuna amb la seva superfície, els seus paràmetres i el
// seu plànol. Cada part és un registre sencer; la pàgina en mostra una i deixa triar.
const VOLUM = { III: "Vall d'Encamp", IV: 'Els Cortals', V: 'Pas de la Casa',
                VI: 'Sòl urbanitzable', VII: 'Sòl no urbanitzable' };

// A la pestanya UA hi ha unitats amb una fila per volum (Salitar i Lloset 2: una de la
// part urbana i una de la de sòl no urbanitzable). No són duplicats: són la mateixa
// unitat amb dues qualificacions. Les parts surten de les fitxes, o sigui que aquí n'hi
// ha prou de quedar-se una fila per unitat, i que sigui la urbana: és la que porta el
// nom i el tipus de fitxa que encapçalen la unitat.
const filesUA = new Map();
const clsVolum = new Map();      // id_ua|volum -> classificació, quan la fila del volum hi és
for (const u of F.UA) {
  const id = (u.id_ua || '').trim();
  if (!id || !(u.nom_oficial || '').trim()) continue;
  // només val si la fila és d'un sol volum: si en cobreix uns quants, la seva
  // classificació és la de la part urbana i no diu res de la de sòl no urbanitzable
  const vols1 = (u.volums || '').split(/[;\s]+/).filter(Boolean);
  if (vols1.length === 1 && !clsVolum.has(id + '|' + vols1[0]))
    clsVolum.set(id + '|' + vols1[0], u.classificacio_vigent);
  const hi = filesUA.get(id);
  if (!hi || (hi.volums === 'VII' && u.volums !== 'VII')) filesUA.set(id, u);
}

const UA = [];
for (const u of filesUA.values()) {
  const idu = (u.id_ua || '').trim();
  const fs = fitxes[idu] || [];
  const vig = fs.filter(f => f.vigent === 'SÍ');
  const perVolum = new Map();
  for (const f of (vig.length ? vig : fs.slice(0, 1)))
    if (!perVolum.has(f.volum)) perVolum.set(f.volum, f);
  const ov = overrides[idu] || {};

  const rec = { id: idu, n: ov.nom_public || u.nom_oficial, tf: u.tipus_fitxa, parts: [], fx: [] };

  const vols = [...perVolum.keys()].sort((x, y) =>
    (x === 'VII' ? 1 : 0) - (y === 'VII' ? 1 : 0) || String(x).localeCompare(String(y)));

  for (const vol of vols) {
    const principal = perVolum.get(vol);
    const p = pf[principal.id_fitxa] || {};
    const z = parseClaus(p.zones), sz = parseClaus(p.subzones);

    const part = {
      vol, idf: principal.id_fitxa, np: VOLUM[vol] || ('Volum ' + vol),
      // el volum VII és, per definició, sòl no urbanitzable: quan la fitxa no diu la
      // classificació, val més això que no pas heretar la de la part urbana
      cls: p.classificacio || clsVolum.get(idu + '|' + vol)
           || (vol === 'VII' ? 'SNUBLE' : u.classificacio_vigent),
      // el tipus surt de la fitxa de la part, no de la unitat: una unitat pot ser
      // «UA per subzona» a la part urbana i «àrea diferenciada» a la de SNU
      tf: principal.tipus_fitxa || u.tipus_fitxa,
      // amb dues parts, cadascuna ha de dur la seva: la superfície de la unitat sencera
      // repetida a totes dues enganyaria, i el plànol la comptaria dos cops.
      sup: p.superficie_m2 || (vols.length > 1 ? '' : u.superficie_vigent) || '',
      cob: p.cobertura || '', edif: p.edificabilitat_max_m2 || '',
      z, sz, clau: [z.map(x => x.c).join('·'), sz.map(x => x.c).join('·')].filter(Boolean).join(' / '),
      raw: {}, av: [], pr: [],
    };
    if (p.ordenacio) part.raw.o = p.ordenacio;
    if (p.usos) part.raw.u = p.usos;
    if (p.gestio) part.raw.g = p.gestio;

    // resum
    if (ov.resum_que_es) {
      part.res = [ov.resum_que_es, ov.resum_que_shi_pot_fer, ov.resum_com_es_desenvolupa];
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
    const ids = [];
    const mapa2 = { SUBLE: 'AV1', SUNC: 'AV2', SNUBLE: 'AV3', SNU: 'AV3' };
    if (mapa2[part.cls]) ids.push(mapa2[part.cls]);
    if (part.tf === 'àrea diferenciada') ids.push('AV4');
    if (part.tf === 'UA definició volumètrica') ids.push('AV5');
    if (prot[idu]) ids.push('AV6');
    if (fs.some(f => f.modificacio !== 'M00')) ids.push('AV7');
    if ((part.cob || '').includes('sense aprofitament privat')) ids.push('AV8');
    part.av = ids.filter(i => avisos[i]).map(i => ({ ...avisos[i] }));
    if (ov.avis_propi) part.av.push({ to: 'atencio', x: ov.avis_propi });

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

  // fitxes: totes, amb el volum a què pertanyen
  for (const f of [...fs].sort((a, b) => (a.vigent === 'SÍ' ? 0 : 1) - (b.vigent === 'SÍ' ? 0 : 1)
                                      || String(a.volum).localeCompare(String(b.volum))
                                      || String(a.modificacio).localeCompare(String(b.modificacio))))
    rec.fx.push({ idf: f.id_fitxa, m: f.modificacio, v: f.volum, vig: f.vigent === 'SÍ',
                  fase: f.fase_aprovacio, b: `BOPA núm. ${f.bopa_num}, ${f.bopa_data}`,
                  pg: f.bopa_pagina, pdf: f.drive_id, img: img[f.id_fitxa] || '' });
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

// Geometria de les unitats, treta del DWG cadastral (mira scripts/dwg-a-mapa.py).
let mapa = null;
try {
  mapa = JSON.parse(await readFile(ARREL + 'data/mapa.json', 'utf8'));
  // Les parcel·les del cadastre es guarden al fitxer però ara no es publiquen: el
  // plànol només ensenya les unitats. Treu aquesta línia per tornar-les a enviar.
  delete mapa.p;
  mapa.n = Object.keys(mapa.ua).filter(id => UA.some(u => u.id === id)).length;
  for (const id of Object.keys(mapa.ua)) if (!UA.some(u => u.id === id)) delete mapa.ua[id];
  console.log(`\nPlànol: ${mapa.n} unitats amb perímetre`);
} catch { console.log('\nSense data/mapa.json: la web sortirà sense plànol.'); }

const data = { pool, cfg, T, blocs, params, claus, variants, valors, arts, ua: UA, mapa,
               glossari: C.glossari_public.filter(g => g.visible === 'SÍ')
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
for (const r of F.Normativa_apartats) {
  if (!citats.has(r.article)) continue;
  (artsEsq[r.article] ||= { t: r.titol_article, f: r.bopa, ap: [] })
    .ap.push([r.apartat, (r.text || '').trim()]);
}
// els articles de zona i subzona porten tots els paràmetres en un sol apartat inacabable;
// la pestanya Claus_parametres els té partits per lletra, que és com es llegeixen
const clausArt = {};
for (const r of F.Claus_parametres) {
  if (!citats.has(r.article)) continue;
  (clausArt[r.article] ||= []).push({
    c: r.clau, l: r.lletra, p: r.parametre, v: r.valor,
    n: r.valor_numeric, u: r.unitat, r: r.remet_a });
}
await writeFile(ARREL + 'public/esquema.html',
  embolcalla(brutEsq.replace('__CLAUS__', () => JSON.stringify(clausArt).replace(/</g, '\\u003c'))
    .replace('__ARTICLES__',
    () => JSON.stringify(artsEsq).replace(/</g, '\\u003c')),
    "Quin nivell del POUPE d'Encamp decideix cada paràmetre: la fitxa, la subzona, la zona o les normes genèriques."));
console.log(`Esquema: ${Object.keys(artsEsq).length} articles incrustats a public/esquema.html`);

console.log(`\nFet: ${UA.length} unitats · ${Math.round(JSON.stringify(data).length / 1024)} KB a public/data.json`);

/**
 * Ensenya com el build veu una pestanya del full. Serveix per a quan el build es
 * queixa i no queda clar per què: aquí es veu exactament què arriba.
 *
 *   node scripts/mira-pestanya.mjs unitats
 *   node scripts/mira-pestanya.mjs fitxes 3
 */
import { FULL } from './config.mjs';

const nom = process.argv[2];
const quantes = Number(process.argv[3] || 2);
if (!nom) {
  console.error('Digues quina pestanya: node scripts/mira-pestanya.mjs unitats');
  process.exit(1);
}

const url = `https://docs.google.com/spreadsheets/d/${FULL}/gviz/tq?tqx=out:csv&headers=1&sheet=${encodeURIComponent(nom)}`;
const r = await fetch(url);
if (!r.ok) {
  console.error(`No s'ha pogut llegir «${nom}» (${r.status}). El full està compartit amb enllaç?`);
  process.exit(1);
}
const t = await r.text();
if (t.startsWith('<')) {
  console.error(`«${nom}» ha tornat HTML: o el full no és públic, o la pestanya no existeix.`);
  process.exit(1);
}

const linies = t.split('\n').filter(l => l.trim());
console.log(`«${nom}»: ${linies.length - 1} files\n`);
console.log('Capçaleres, tal com les llegeix el build:');
for (const [i, c] of (linies[0] || '').split(',').entries())
  console.log(`  ${String(i + 1).padStart(2)}  ${c.replace(/^"|"$/g, '')}`);
console.log('\nPrimeres files:');
for (const l of linies.slice(1, 1 + quantes)) console.log('  ' + l.slice(0, 200));

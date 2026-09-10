# -*- coding: utf-8 -*-
"""Del DWG cadastral a data/mapa.json.

El DWG porta, en capes separades, els perímetres de les unitats d'actuació
(«01 1 UA SUC», «01 2 UA SUNC»…), els noms de les unitats («ÀMBITS NOM») i les
parcel·les del cadastre (capes numèriques 1402xx). Aquest guió els treu, casa
cada nom amb la unitat que li toca i escriu la geometria simplificada.

Fa falta LibreDWG per llegir el DWG:

    git clone --depth 1 https://github.com/LibreDWG/libredwg
    cd libredwg && ./configure --disable-bindings && make
    ./programs/dwgread -O JSON -o parcelles.json Parcelles_UAs.dwg

I pyproj, per passar les coordenades del cadastre (NTF Lambert Sud, EPSG:27563)
a les del web (Web Mercator, EPSG:3857), que és el que fan servir els mapes de
fons de qualsevol proveïdor:

    pip install pyproj

I després:

    python scripts/dwg-a-mapa.py parcelles.json public/data.json data/mapa.json

El segon argument és un data.json ja generat: serveix per saber els noms i els
identificadors de les unitats amb què s'han de casar les etiquetes del plànol.
"""
import json, sys, math, re, unicodedata, collections
from pyproj import Transformer

# El DWG del cadastre va en NTF (Paris) / Lambert Sud, el sistema històric d'Andorra.
# La web el vol en Web Mercator, que és el dels mapes de fons.
CADASTRE, WEB = 'EPSG:27563', 'EPSG:3857'
_tr = Transformer.from_crs(CADASTRE, WEB, always_xy=True)
projecta = lambda p: [_tr.transform(x, y) for x, y in p]

# Només les capes d'unitats d'actuació. Les altres capes «01 …» del DWG —sòl privat
# en SNU per risc, sòl comunal— no són unitats, i barrejar-les feia que una etiqueta
# s'enganxés al recinte del costat.
CAPES_UA = {'01 1 UA SUC': 'SUC', '01 2 UA SUNC': 'SUNC',
            '01 3 UA SUBLE': 'SUBLE', '01 11 UA SUCc': 'SUCc'}
CAPA_NOMS = 'ÀMBITS NOM'
CAPA_SUP = '_Sup UA'      # el DWG escriu la superfície de cada recinte a dins seu
TOL = 1.0          # simplificació, en metres
# Quant es pot allunyar l'àrea dibuixada de la superfície que diu la fitxa. Per a la
# majoria la diferència és de dècimes; un 15% deixa passar les poques on la fitxa i el
# dibuix no es van actualitzar alhora, i encara descarta els recintes que no toquen.
TOL_AREA = 0.15
# Quan la superfície no quadra però el nom és escrit dins d'un recinte que no vol ningú
# més, s'accepta mentre el recinte no sigui desproporcionat: fins al doble amunt
# o avall. Més enllà, l'etiqueta ha caigut damunt d'un veí i no és seva.
LIMIT_DINS = 2.0
# Noms que al DWG s'escriuen diferent que a les fitxes. La clau i el valor van
# passats per nrm(): tot en minúscules, sense accents ni punts.
ALIES = {
    'es esso': 'esso',              # «E.S. Esso» al DWG, «ESSO» a les fitxes
    'es figueredo': 'figueredo',
    'es mobil': 'mobil',
    'es arajol': 'arajol',
}


def nrm(s):
    s = unicodedata.normalize('NFD', (s or '').lower())
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]+', ' ', s.replace('·', '').replace('.', '')).strip()


def llegeix(dwg_json):
    d = json.load(open(dwg_json, encoding='latin-1'))
    obs = d['OBJECTS']
    capes = {o['handle'][2]: o.get('name') for o in obs
             if o.get('object') == 'LAYER' and isinstance(o.get('handle'), list)}

    def capa(o):
        lh = o.get('layer')
        return capes.get(lh[2], '') if isinstance(lh, list) and len(lh) > 2 else ''

    polis, noms, parcelles = [], [], []
    # Tot es queda en coordenades del cadastre: són metres de veritat, i les àrees i
    # distàncies del repartiment es calculen aquí. La projecció ve al final.
    for o in obs:
        e, c = o.get('entity'), capa(o)
        if e == 'LWPOLYLINE':
            pts = [p[:2] for p in o.get('points', [])]
            if len(pts) < 3:
                continue
            if c in CAPES_UA:
                polis.append(pts)
            elif c.startswith('1400') or c.startswith('1402'):
                parcelles.append(pts)
        elif e in ('TEXT', 'MTEXT') and c in (CAPA_NOMS, CAPA_SUP):
            t = o.get('text_value') if e == 'TEXT' else re.sub(r'\\[A-Za-z][^;]*;|[{}]', '', o.get('text', ''))
            t = (t or '').strip()
            if t:
                noms.append({'t': t, 'x': o['ins_pt'][0], 'y': o['ins_pt'][1], 'sup': c == CAPA_SUP})
    return polis, [n for n in noms if not n['sup']], parcelles


def dins(pt, poly):
    x, y = pt
    a = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            a = not a
    return a


def dp(pts, tol):
    """Douglas–Peucker."""
    if len(pts) < 3:
        return pts
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    dx, dy = x2 - x1, y2 - y1
    n2 = dx * dx + dy * dy
    dmax, idx = 0, 0
    for i in range(1, len(pts) - 1):
        x, y = pts[i]
        # forma estable: es resta primer l'origen del segment. Amb les coordenades
        # de Web Mercator (7 xifres) la forma clàssica perd tota la precisió.
        d = abs((x - x1) * dy - (y - y1) * dx) / math.sqrt(n2) if n2 else math.dist(pts[i], pts[0])
        if d > dmax:
            dmax, idx = d, i
    return dp(pts[:idx + 1], tol)[:-1] + dp(pts[idx:], tol) if dmax > tol else [pts[0], pts[-1]]


def comprimeix(anell, ox, oy):
    """Simplifica, arrodoneix al metre i guarda deltes entre vèrtexs."""
    if anell[0] == anell[-1]:
        anell = anell[:-1]
    s = dp(anell, TOL)
    ent, vist = [], None
    for x, y in s:
        p = (round(x - ox), round(y - oy))
        if p != vist:
            ent.append(p)
            vist = p
    if len(ent) < 3:
        return None
    d = [ent[0][0], ent[0][1]]
    for i in range(1, len(ent)):
        d += [ent[i][0] - ent[i - 1][0], ent[i][1] - ent[i - 1][1]]
    return d


def main(dwg_json, data_json, sortida):
    polis_ll, noms, parcelles_ll = llegeix(dwg_json)
    # A les capes de les unitats hi ha també polilínies que no tanquen cap recinte:
    # línies de guia i punts. Si es deixen, s'enduen etiquetes que toquen a un polígon
    # de debò i la unitat es queda sense dibuix.
    def area(p):
        a = 0
        for i in range(len(p)):
            (x1, y1), (x2, y2) = p[i], p[(i + 1) % len(p)]
            a += x1 * y2 - x2 * y1
        return abs(a) / 2
    polis = [p for p in polis_ll if area(p) > 50]
    print(f'polígons: {len(polis)} (n\'hi havia {len(polis_ll)}; la resta són línies o punts)')
    web = json.load(open(data_json, encoding='utf-8'))
    per_nom = collections.defaultdict(list)
    for u in web['ua']:
        per_nom[nrm(u['n'])].append(u['id'])

    def busca(t):
        k = nrm(t)
        return per_nom.get(k) or per_nom.get(ALIES.get(k, '\0'))

    # etiquetes: primer les de tres línies, després les de dues i les d'una,
    # perquè «Envalira» + «de Dalt 3» no es mengi la unitat que es diu «Envalira».
    usat = [False] * len(noms)
    etiquetes = []
    for k in (3, 2, 1):
        for i, n in enumerate(noms):
            if usat[i]:
                continue
            if k == 1:
                ids = busca(n['t'])
                if ids:
                    usat[i] = True
                    etiquetes.append({'id': ids[0], 'x': n['x'], 'y': n['y']})
                continue
            prop = sorted((j for j, m in enumerate(noms)
                           if not usat[j] and j != i and abs(m['x'] - n['x']) < 30
                           and 0 < abs(m['y'] - n['y']) < 14),
                          key=lambda j: abs(noms[j]['y'] - n['y']))[:k - 1]
            if len(prop) < k - 1:
                continue
            grup = sorted([i] + prop, key=lambda j: -noms[j]['y'])
            ids = busca(' '.join(noms[j]['t'] for j in grup))
            if ids:
                for j in grup:
                    usat[j] = True
                etiquetes.append({'id': ids[0],
                                  'x': sum(noms[j]['x'] for j in grup) / k,
                                  'y': sum(noms[j]['y'] for j in grup) / k})

    caixes = [(min(q[0] for q in p), min(q[1] for q in p),
               max(q[0] for q in p), max(q[1] for q in p)) for p in polis]
    arees = [area(p) for p in polis]

    def lluny(i, pt):    # distància a la caixa del recinte, no al seu centre
        b = caixes[i]
        return math.hypot(max(b[0] - pt[0], 0, pt[0] - b[2]), max(b[1] - pt[1], 0, pt[1] - b[3]))

    def a_dins(i, pt):
        b = caixes[i]
        return b[0] <= pt[0] <= b[2] and b[1] <= pt[1] <= b[3] and dins(pt, polis[i])

    # La superfície de la fitxa és la clau del repartiment: el DWG està ben grafiat i
    # l'àrea de cada recinte hi coincideix. El nom serveix per desempatar entre recintes
    # de mida semblant, perquè al DWG moltes etiquetes cauen fora del seu recinte.
    # Una unitat pot tenir més d'una part (una fitxa per volum del pla: la urbana i la
    # de sòl no urbanitzable), cadascuna amb la seva superfície i el seu recinte. Cada
    # part és un objectiu de repartiment independent; al final es tornen a ajuntar sota
    # la unitat, que és com les dibuixa la pàgina.
    def num(t):
        try:
            v = float(str(t).replace('.', '').replace(',', '.').strip())
            return v if v > 0 else None
        except ValueError:
            return None

    objectius, sup = [], {}
    for u in web['ua']:
        parts = u.get('parts') or [u]
        for k, pt in enumerate(parts):
            v = num(pt.get('sup', ''))
            if v:
                objectius.append({'ua': u['id'], 'k': f"{u['id']}#{k}", 's': v})
        tot = [num(pt.get('sup', '')) for pt in parts]
        tot = [x for x in tot if x]
        if tot:
            sup[u['id']] = sum(tot)

    punts_ua = collections.defaultdict(list)
    for et in etiquetes:
        punts_ua[et['id']].append((et['x'], et['y']))

    # --- 1) parts d'una sola peça: un recinte que fa la superfície de la fitxa
    parelles = []
    for ob in objectius:
        pts = punts_ua.get(ob['ua'])
        if not pts:
            continue
        s_ua = ob['s']
        for i in range(len(polis)):
            err = abs(arees[i] - s_ua) / s_ua
            if err > TOL_AREA:
                continue
            d = min(lluny(i, pt) for pt in pts)
            if d > 400:
                continue
            dins_ = any(a_dins(i, pt) for pt in pts)
            parelles.append((err * 20 + d / 300 + (0 if dins_ else 0.4), ob['k'], i))

    parelles.sort()
    fet, presos = collections.defaultdict(list), set()
    for _, k, i in parelles:
        if k in fet or i in presos:
            continue
        fet[k].append(i)
        presos.add(i)
    print(f'   d\'una peça: {len(fet)} parts')

    # --- 2) parts de diverses peces: se sumen recintes propers fins a fer la superfície
    for ob in objectius:
        idu, pts = ob['ua'], punts_ua.get(ob['ua'])
        s_ua = ob['s']
        if ob['k'] in fet or not pts:
            continue
        prop = sorted((i for i in range(len(polis))
                       if i not in presos and min(lluny(i, pt) for pt in pts) < 250
                       and arees[i] <= s_ua * (1 + TOL_AREA)),
                      key=lambda i: (0 if any(a_dins(i, pt) for pt in pts) else 1,
                                     min(lluny(i, pt) for pt in pts)))
        tros, tot = [], 0.0
        for i in prop:
            if tot + arees[i] > s_ua * (1 + TOL_AREA):
                continue
            tros.append(i); tot += arees[i]
            if tot >= s_ua * (1 - TOL_AREA):
                break
        if tros and abs(tot - s_ua) / s_ua <= TOL_AREA:
            fet[ob['k']] = tros
            presos.update(tros)
    print(f'   amb les de diverses peces: {len(fet)} parts')

    # les parts tornen a la seva unitat: la pàgina dibuixa per unitat
    casat = collections.defaultdict(list)
    for k, idxs in fet.items():
        casat[k.split('#')[0]].extend(idxs)
    casat = collections.defaultdict(list, {k: v for k, v in casat.items() if v})
    print(f'   -> {len(casat)} unitats')

    # --- 3) l'última xarxa: el nom cau dins d'un recinte lliure. La superfície de la
    # fitxa i la del dibuix no s'assemblen, però el nom escrit a dins d'un recinte que
    # no vol ningú més és prou senyal. Si el recinte és desproporcionat (l'etiqueta ha
    # caigut damunt d'un veí molt més gros), es deixa córrer.
    for idu, pts in punts_ua.items():
        if idu in casat:
            continue
        s_ua = sup.get(idu)
        dins_lliures = sorted((i for i in range(len(polis))
                               if i not in presos and any(a_dins(i, pt) for pt in pts)),
                              key=lambda i: arees[i])
        for i in dins_lliures:
            if s_ua and not (s_ua / LIMIT_DINS <= arees[i] <= s_ua * LIMIT_DINS):
                continue
            casat[idu] = [i]; presos.add(i)
            break
    print(f'   amb les que el nom cau dins d\'un recinte lliure: {len(casat)} unitats')

    # ara sí: a Web Mercator
    bons = sorted({i for v in casat.values() for i in v})
    proj_ua = {i: projecta(polis[i]) for i in bons}
    proj_par = [projecta(p) for p in parcelles_ll]
    xs = [q[0] for i in bons for q in proj_ua[i]]
    ys = [q[1] for i in bons for q in proj_ua[i]]
    ox, oy = math.floor(min(xs)), math.floor(min(ys))

    ua = {}
    for idu, idxs in casat.items():
        anells = [a for a in (comprimeix(proj_ua[i], ox, oy) for i in idxs) if a]
        if anells:
            ua[idu] = anells
    par = [a for a in (comprimeix(p, ox, oy) for p in proj_par) if a]

    json.dump({'o': [ox, oy], 'ua': ua, 'p': par}, open(sortida, 'w'), separators=(',', ':'))
    print(f'{len(ua)} unitats amb perímetre, {len(par)} parcel·les -> {sortida}')
    sense = [u['n'] for u in web['ua'] if u['id'] not in ua]
    print(f'sense geometria ({len(sense)}):', ', '.join(sorted(sense)))


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])

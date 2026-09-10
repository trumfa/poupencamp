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
TOL_AREA = 0.20
# Quan la superfície no quadra però el nom és escrit dins d'un recinte que no vol ningú
# més, s'accepta mentre el recinte no sigui desproporcionat: fins al doble amunt
# o avall. Més enllà, l'etiqueta ha caigut damunt d'un veí i no és seva.
LIMIT_DINS = 2.0
# Quan el recinte es guanya pel nom i la qualificació, i no pels metres, la superfície de
# la fitxa encara serveix per a una cosa: descartar disbarats. Un factor de quinze deixa
# passar les fitxes amb el punt dels milers mal posat (Feda 4 diu «3.04» i el recinte fa
# 3.032 m²) i atura les etiquetes que han caigut damunt d'un veí molt més gros.
LIMIT_NOM = 15.0
# Unitats on la superfície de la fitxa i la del dibuix no s'assemblen i ja s'ha mirat
# què passa: el dibuix es queda com és i no cal que l'informe hi torni cada vegada.
ACCEPTATS = {
    'CRESPER': 'el recinte gros del costat és del veí; cadascú el seu, encara que la fitxa digui més',
    'PARDINES_3': 'un recinte per a Pardines 3 i un per a Pardines 2, encara que els metres no quadrin',
    'PAS_DE_LA_CASA_1': 'la fitxa es queda curta; el recinte del DWG és el bo',
}
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
                polis.append((pts, CAPES_UA[c]))
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
    polis = [p for p, _ in polis_ll if area(p) > 50]
    # la capa del DWG diu la classificació de cada recinte: SUC, SUNC, SUBLE, SUCc
    cls_poli = [c for p, c in polis_ll if area(p) > 50]
    print(f'polígons: {len(polis)} (n\'hi havia {len(polis_ll)}; la resta són línies o punts)')
    print('   per classificació:', dict(collections.Counter(cls_poli)))
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

    pool = web.get('pool') or []
    txt = lambda x: pool[x] if isinstance(x, int) and 0 <= x < len(pool) else (x or '')

    objectius, sup = [], {}
    for u in web['ua']:
        parts = u.get('parts') or [u]
        for k, pt in enumerate(parts):
            objectius.append({'ua': u['id'], 'k': f"{u['id']}#{k}",
                              's': num(pt.get('sup', '')), 'cls': txt(pt.get('cls'))})
        tot = [num(pt.get('sup', '')) for pt in parts]
        tot = [x for x in tot if x]
        if tot:
            sup[u['id']] = sum(tot)

    # La capa del DWG diu la classificació de cada recinte i la fitxa diu la de cada part:
    # quan totes dues coincideixen, el recinte és candidat; quan no, gairebé mai ho és.
    # SUC i SUCc són la mateixa classificació amb dos graus de consolidació, així que es
    # deixen passar l'una per l'altra, però amb penalització.
    PARENT = {'SUC': 'SUC', 'SUCc': 'SUC', 'SUNC': 'SUNC', 'SUBLE': 'SUBLE'}

    def encaix(c_part, i):
        c_poli = cls_poli[i]
        if c_part == c_poli:
            return 0.0
        if PARENT.get(c_part) and PARENT.get(c_part) == PARENT.get(c_poli):
            return 0.3
        # Les quatre capes del DWG són totes de sòl urbà o urbanitzable. Una part de sòl
        # no urbanitzable no hi té recinte: no pot prendre'n cap, ni que la superfície
        # quadri. Abans en prenia, i la unitat sortia dibuixada al tros que no tocava.
        return None

    punts_ua = collections.defaultdict(list)
    for et in etiquetes:
        punts_ua[et['id']].append((et['x'], et['y']))

    # El nom escrit dins d'un recinte és el senyal més fort que hi ha, i la qualificació
    # de la capa el confirma. Però al DWG hi ha etiquetes amb línia de guia que cauen
    # damunt del recinte del veí, i hi ha fitxes amb la superfície mal escrita. Per això
    # no hi ha una regla que mani sobre les altres, sinó una nota per a cada parella
    # (part, recinte): com més baixa, més convincent. Es reparteix de la millor a la
    # pitjor i cap recinte no és de dues parts.
    clas_ua = collections.defaultdict(set)
    for ob in objectius:
        clas_ua[ob['ua']].add(ob['cls'])

    punts_ua = collections.defaultdict(list)
    for et in etiquetes:
        punts_ua[et['id']].append((et['x'], et['y']))

    # De qui és el nom que hi ha escrit dins de cada recinte. Només compta si la unitat
    # té una part de la qualificació del recinte: si no, l'etiqueta hi és de pas.
    propietari = {}
    for i in range(len(polis)):
        qui = {idu for idu, pts in punts_ua.items()
               if any(a_dins(i, pt) for pt in pts)
               and any(encaix(c, i) is not None and encaix(c, i) <= 0.5
                       for c in clas_ua.get(idu, ()))}
        propietari[i] = qui.pop() if len(qui) == 1 else None
    print(f'   recintes amb un sol nom a dins: {sum(1 for v in propietari.values() if v)}')

    parelles = []
    for ob in objectius:
        pts = punts_ua.get(ob['ua'])
        if not pts:
            continue
        for i in range(len(polis)):
            q = encaix(ob['cls'], i)
            if q is None:                       # qualificació incompatible: mai
                continue
            d = min(lluny(i, pt) for pt in pts)
            if d > 400:
                continue
            meu = any(a_dins(i, pt) for pt in pts)
            altre = propietari[i] not in (None, ob['ua'])
            # quan la part no diu la superfície, es fa servir la de la unitat sencera
            # per no acceptar disbarats; si no n'hi ha cap, es passa sense comprovar
            ref = ob['s'] or sup.get(ob['ua'])
            if ob['s'] and abs(arees[i] - ob['s']) / ob['s'] <= TOL_AREA:
                base = abs(arees[i] - ob['s']) / ob['s'] * 20   # 0 – 3: la superfície quadra
            elif meu and (not ref or 1 / LIMIT_NOM <= arees[i] / ref <= LIMIT_NOM):
                base = 3.5                      # el nom hi és, però els metres no quadren
            else:
                continue
            parelles.append((base + d / 300 + (0 if meu else 0.4) + q + (2.0 if altre else 0),
                             ob['k'], i))

    parelles.sort()
    fet, presos, per_nom = collections.defaultdict(list), set(), set()

    def reparteix(mena):
        n = 0
        for nota, k, i in parelles:
            if (nota < 3.5) != mena or k in fet or i in presos:
                continue
            fet[k].append(i)
            presos.add(i)
            n += 1
            if not mena:
                per_nom.add(k)
        return n

    # Primer les parelles que quadren de superfície, que són les de fiar. Les que només
    # tenen el nom a favor esperen: si es repartissin ara, prendrien un tros a una unitat
    # de diverses peces que encara l'ha de reunir.
    print(f'   per superfície: {reparteix(True)} parts')

    # --- parts de diverses peces: se sumen recintes propers, de la mateixa qualificació,
    # fins a fer la superfície de la fitxa. Hi entren tant les parts que encara no tenen
    # cap recinte com les que només en tenen un de guanyat pel nom i que es queden curtes:
    # les unitats grans de fora del nucli el DWG les dibuixa a trossos.
    def peces():
        n = 0
        for ob in objectius:
            pts = punts_ua.get(ob['ua'])
            if not pts or not ob['s'] or (ob['k'] in fet and ob['k'] not in per_nom):
                continue
            s_ua = ob['s']
            tros = list(fet.get(ob['k'], []))
            tot = sum(arees[i] for i in tros)
            if tot >= s_ua * (1 - TOL_AREA):
                continue
            prop = sorted((i for i in range(len(polis))
                           if i not in presos and encaix(ob['cls'], i) is not None
                           and propietari[i] in (None, ob['ua'])
                           and min(lluny(i, pt) for pt in pts) < 250
                           and arees[i] <= s_ua * (1 + TOL_AREA)),
                          key=lambda i: (0 if any(a_dins(i, pt) for pt in pts) else 1,
                                         min(lluny(i, pt) for pt in pts)))
            for i in prop:
                if tot + arees[i] > s_ua * (1 + TOL_AREA):
                    continue
                tros.append(i); tot += arees[i]
                if tot >= s_ua * (1 - TOL_AREA):
                    break
            if tros and abs(tot - s_ua) / s_ua <= TOL_AREA:
                per_nom.discard(ob['k'])
                fet[ob['k']] = tros
                presos.update(tros)
                n += 1
        return n

    print(f'   sumant peces: {peces()} parts més')

    # Ara sí, les que només tenen el nom i la qualificació a favor: la superfície de la
    # fitxa no quadra amb cap recinte, sovint perquè la fitxa la porta mal escrita.
    print(f'   pel nom i la qualificació: {reparteix(False)} parts més')
    print(f'   i completant-les amb els trossos del voltant: {peces()} parts més')

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
    # Quan una unitat es guanya el recinte pel nom i la qualificació però els metres no
    # s'assemblen als de la fitxa, gairebé sempre és la fitxa que els porta mal escrits
    # (un punt de milers de menys). Val la pena dir-ho: es corregeix al full i tot quadra.
    noms_ua = {u['id']: u['n'] for u in web['ua']}
    # es compara amb la superfície de les parts que han rebut recinte, no amb la de la
    # unitat sencera: la part de sòl no urbanitzable no es dibuixa i desquadraria el compte
    sup_fet = collections.defaultdict(float)
    for ob in objectius:
        if ob['k'] in fet and ob['s']:
            sup_fet[ob['ua']] += ob['s']
    sospita = []
    for idu, idxs in casat.items():
        s_ua = sup_fet.get(idu)
        if not s_ua:
            continue
        a = sum(arees[i] for i in idxs)
        if not (1 / 1.5 <= a / s_ua <= 1.5) and idu not in ACCEPTATS:
            sospita.append((a / s_ua, noms_ua.get(idu, idu), s_ua, a))
    sospita.sort(key=lambda r: -abs(math.log(r[0])))
    print(f'\nsuperfícies que no s\'assemblen a les del dibuix ({len(sospita)}), '
          f'per revisar al full:')
    for r, n, s_ua, a in sospita:
        print(f'   {n[:34]:<34} fitxa {s_ua:>10,.0f}   dibuix {a:>10,.0f}   x{r:.1f}'
              .replace(',', '.'))

    sense = [u['n'] for u in web['ua'] if u['id'] not in ua]
    print(f'sense geometria ({len(sense)}):', ', '.join(sorted(sense)))


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])

# -*- coding: utf-8 -*-
"""Ha arribat un plànol nou.

Llegeix un GeoJSON o un DWG i el compara amb els recintes que ja hi ha al full. No
reassigna res: cada recinte surt marcat com a IGUAL, NOU, CANVIAT o DESAPAREGUT, i
les files que ja has revisat no es toquen mai.

    python scripts/planol-nou.py planol.geojson data/ [recintes.csv] [unitats.csv]

  planol.geojson   el plànol nou. També s'accepta el JSON que surt de LibreDWG:
                       dwgread -O JSON -o planol.json Parcelles_UAs.dwg
  data/            on s'escriuen els tres fitxers de sortida
  recintes.csv     la pestanya «recintes» del full, exportada. Si no s'hi posa,
                   es comença de zero i tots els recintes surten com a NOUS.
  unitats.csv      la pestanya «unitats», per proposar l'assignació dels nous a
                   partir del nom escrit dins del recinte.

En surten:

    data/recintes.geojson   el plànol net, en EPSG:4326, per a qui el vulgui obrir
    data/geometria.json     el mateix, per al navegador: Web Mercator i deltes
    data/recintes.csv       la taula per enganxar al full, amb la columna «canvi»

Cal pyproj. Si l'entrada és un DWG, cal també LibreDWG.
"""
import json, csv, sys, os, math, re, collections, unicodedata
from pyproj import Transformer

CADASTRE, WGS84, WEB = 'EPSG:27563', 'EPSG:4326', 'EPSG:3857'
CAPES_UA = {'01 1 UA SUC': 'SUC', '01 2 UA SUNC': 'SUNC',
            '01 3 UA SUBLE': 'SUBLE', '01 11 UA SUCc': 'SUCc'}
CAPA_NOMS = 'ÀMBITS NOM'
AREA_MIN = 50.0            # per sota d'això no és un recinte: és una línia de guia
PROP_M, PROP_AREA = 2.0, 0.01     # quan dos recintes de dos plànols són el mateix
TOL_DP = 1.0               # simplificació, en metres


# ------------------------------------------------------------------ geometria
def area(p):
    a = 0.0
    for i in range(len(p)):
        (x1, y1), (x2, y2) = p[i], p[(i + 1) % len(p)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2


def centre(p):
    return (sum(q[0] for q in p) / len(p), sum(q[1] for q in p) / len(p))


def dins(pt, poly):
    x, y = pt
    a = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            a = not a
    return a


def dp(pts, tol):
    """Douglas–Peucker, en la forma estable: amb coordenades de set xifres, la
    clàssica perd tota la precisió i s'empassa polígons sencers."""
    if len(pts) < 3:
        return pts
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    dx, dy = x2 - x1, y2 - y1
    n2 = dx * dx + dy * dy
    dmax, idx = 0, 0
    for i in range(1, len(pts) - 1):
        x, y = pts[i]
        d = abs((x - x1) * dy - (y - y1) * dx) / math.sqrt(n2) if n2 else math.dist(pts[i], pts[0])
        if d > dmax:
            dmax, idx = d, i
    return dp(pts[:idx + 1], tol)[:-1] + dp(pts[idx:], tol) if dmax > tol else [pts[0], pts[-1]]


def comprimeix(anell, ox, oy):
    """Simplifica al metre i guarda deltes entre vèrtexs."""
    if anell[0] == anell[-1]:
        anell = anell[:-1]
    ent, vist = [], None
    for x, y in dp(anell, TOL_DP):
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


def nrm(s):
    s = unicodedata.normalize('NFD', (s or '').lower())
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]+', ' ', s.replace('·', '').replace('.', '')).strip()


# ------------------------------------------------------------------ entrades
def llegeix_dwg(cami):
    """El bolcat de LibreDWG. Les coordenades són del cadastre, EPSG:27563."""
    d = json.load(open(cami, encoding='latin-1'))
    obs = d['OBJECTS']
    capes = {o['handle'][2]: o.get('name') for o in obs
             if o.get('object') == 'LAYER' and isinstance(o.get('handle'), list)}

    def capa(o):
        lh = o.get('layer')
        return capes.get(lh[2], '') if isinstance(lh, list) and len(lh) > 2 else ''

    recs, noms = [], []
    for o in obs:
        e, c = o.get('entity'), capa(o)
        if e == 'LWPOLYLINE' and c in CAPES_UA:
            pts = [p[:2] for p in o.get('points', [])]
            if len(pts) >= 3 and area(pts) > AREA_MIN:
                recs.append({'pts': pts, 'capa': c, 'cls': CAPES_UA[c], 'id': ''})
        elif e in ('TEXT', 'MTEXT') and c == CAPA_NOMS:
            t = o.get('text_value') if e == 'TEXT' else re.sub(r'\\[A-Za-z][^;]*;|[{}]', '', o.get('text', ''))
            if (t or '').strip():
                noms.append({'t': t.strip(), 'x': o['ins_pt'][0], 'y': o['ins_pt'][1]})
    return recs, noms, CADASTRE


def llegeix_geojson(cami):
    """Un GeoJSON. Els polígons són els recintes; els punts amb nom, les etiquetes."""
    g = json.load(open(cami, encoding='utf-8'))
    crs = WGS84
    nom_crs = (((g.get('crs') or {}).get('properties') or {}).get('name') or '')
    m = re.search(r'(\d{4,5})$', nom_crs)
    if m and m.group(1) not in ('4326', '84'):
        crs = 'EPSG:' + m.group(1)
    recs, noms = [], []
    for f in g.get('features', []):
        geo, pr = f.get('geometry') or {}, f.get('properties') or {}
        t = geo.get('type')
        if t in ('Polygon', 'MultiPolygon'):
            anells = [geo['coordinates'][0]] if t == 'Polygon' else [p[0] for p in geo['coordinates']]
            for an in anells:
                pts = [(c[0], c[1]) for c in an]
                if pts[0] == pts[-1]:
                    pts = pts[:-1]
                if len(pts) >= 3:
                    recs.append({'pts': pts, 'capa': pr.get('capa_dwg') or pr.get('layer', ''),
                                 'cls': pr.get('classificacio', ''),
                                 'id': pr.get('id_recinte', ''),
                                 'id_ua': pr.get('id_ua', ''),
                                 'nom': pr.get('nom_dwg') or pr.get('nom', '')})
        elif t == 'Point':
            n = pr.get('nom') or pr.get('text') or pr.get('name') or ''
            if n:
                noms.append({'t': str(n), 'x': geo['coordinates'][0], 'y': geo['coordinates'][1]})
    return recs, noms, crs


def etiquetes(noms, per_nom):
    """Del text solt del DWG a etiquetes amb nom d'unitat.

    Dues coses a resoldre. Els noms llargs es dibuixen en dues o tres línies, i cada
    línia és un TEXT a part: «Torrents de l'Obac» + «2». I a la capa hi ha text que no
    és cap unitat —noms de riu, sobretot—, que s'ha de descartar.
    """
    usat = [False] * len(noms)
    out = []
    for k in (3, 2, 1):                       # primer les llargues, que si no «Envalira
        for i, n in enumerate(noms):          # de Dalt 3» se la menja «Envalira»
            if usat[i]:
                continue
            if k == 1:
                idu = per_nom.get(nrm(n['t']))
                if idu:
                    usat[i] = True
                    out.append({'id': idu, 'x': n['x'], 'y': n['y'], 't': n['t']})
                continue
            prop = sorted((j for j, m in enumerate(noms)
                           if not usat[j] and j != i and abs(m['x'] - n['x']) < 30
                           and 0 < abs(m['y'] - n['y']) < 14),
                          key=lambda j: abs(noms[j]['y'] - n['y']))[:k - 1]
            if len(prop) < k - 1:
                continue
            grup = sorted([i] + prop, key=lambda j: -noms[j]['y'])
            text = ' '.join(noms[j]['t'] for j in grup)
            idu = per_nom.get(nrm(text))
            if idu:
                for j in grup:
                    usat[j] = True
                out.append({'id': idu, 't': text,
                            'x': sum(noms[j]['x'] for j in grup) / k,
                            'y': sum(noms[j]['y'] for j in grup) / k})
    return out


def reparteix_noms(recs, etiq):
    """Cada etiqueta a un sol recinte i cada recinte amb un sol nom.

    Una unitat té un nom i prou. Si a dins d'un recinte hi cauen quaranta noms —passa
    al Pas de la Casa, on el dibuix del nucli sencer se'ls empassa tots— vol dir que
    aquelles etiquetes són d'altres recintes, no d'aquell. Per això es reparteixen de
    manera exclusiva: guanya qui la té a dins i és més petit, i després qui la té més a
    prop.
    """
    parelles = []
    for e, et in enumerate(etiq):
        pt = (et['x'], et['y'])
        for i, r in enumerate(recs):
            if r.get('duplicat'):
                continue
            b = r['bb']
            d = math.hypot(max(b[0] - pt[0], 0, pt[0] - b[2]), max(b[1] - pt[1], 0, pt[1] - b[3]))
            if d > 150:
                continue
            a_dins = d == 0 and dins(pt, r['pts'])
            parelles.append(((0 if a_dins else 1), r['area'] if a_dins else d, e, i))
    parelles.sort()
    de_recinte, feta = {}, set()
    for _, _, e, i in parelles:
        if e in feta or i in de_recinte:
            continue
        de_recinte[i] = etiq[e]
        feta.add(e)
    return de_recinte, [etiq[e] for e in range(len(etiq)) if e not in feta]


# ------------------------------------------------------------------ el gruix
def main(entrada, dir_sortida, cami_recintes=None, cami_unitats=None):
    os.makedirs(dir_sortida, exist_ok=True)
    if entrada.lower().endswith(('.geojson', '.json')) and _sembla_geojson(entrada):
        recs, noms, crs = llegeix_geojson(entrada)
        print(f'GeoJSON: {len(recs)} recintes, {len(noms)} etiquetes, {crs}')
    else:
        recs, noms, crs = llegeix_dwg(entrada)
        print(f'DWG: {len(recs)} recintes a les capes d\'unitats, {len(noms)} etiquetes')

    # tot a metres del cadastre, que és on les àrees i les distàncies volen dir alguna cosa
    if crs != CADASTRE:
        tr = Transformer.from_crs(crs, CADASTRE, always_xy=True)
        for r in recs:
            r['pts'] = [tr.transform(x, y) for x, y in r['pts']]
        for n in noms:
            n['x'], n['y'] = tr.transform(n['x'], n['y'])

    recs = [r for r in recs if area(r['pts']) > AREA_MIN]
    for r in recs:
        r['area'] = area(r['pts'])
        r['centre'] = centre(r['pts'])
        r['bb'] = (min(q[0] for q in r['pts']), min(q[1] for q in r['pts']),
                   max(q[0] for q in r['pts']), max(q[1] for q in r['pts']))
    print('   per classificació:', dict(collections.Counter(r['cls'] for r in recs)))

    # Recintes dibuixats dues vegades, un damunt de l'altre. Si es deixen tots dos, la
    # unitat acaba comptant la seva superfície el doble i sembla que no quadri. Es queda
    # el primer i l'altre es marca: no s'esborra, però no es fa servir.
    dobles = 0
    for i in range(len(recs)):
        if recs[i].get('duplicat'):
            continue
        for j in range(i + 1, len(recs)):
            if recs[j].get('duplicat'):
                continue
            if (math.dist(recs[i]['centre'], recs[j]['centre']) < PROP_M
                    and abs(recs[i]['area'] - recs[j]['area']) / max(recs[i]['area'], 1) < PROP_AREA):
                recs[j]['duplicat'] = True
                dobles += 1
    if dobles:
        print(f'   ATENCIÓ: {dobles} recintes hi són dibuixats dues vegades; '
              f'es marquen com a duplicats i no es fan servir')

    # --- els noms: quins són de debò i a quin recinte van
    per_nom = {}
    if cami_unitats and os.path.exists(cami_unitats):
        with open(cami_unitats, encoding='utf-8-sig') as f:
            for u in csv.DictReader(f):
                for n in [u['nom_oficial']] + [x.strip() for x in (u.get('alies') or '').split(';')]:
                    if n:
                        per_nom.setdefault(nrm(n), u['id_ua'])
    nom_ua = {}
    if cami_unitats and os.path.exists(cami_unitats):
        with open(cami_unitats, encoding='utf-8-sig') as f:
            nom_ua = {u['id_ua']: (u['nom_public'] or u['nom_oficial'])
                      for u in csv.DictReader(f)}

    etiq = etiquetes(noms, per_nom) if per_nom else []
    if per_nom:
        de_recinte, orfes = reparteix_noms(recs, etiq)
        for i, r in enumerate(recs):
            e = de_recinte.get(i)
            r['nom'] = nom_ua.get(e['id'], e['t']) if e else ''
            r['nom_id'] = e['id'] if e else ''
        print(f'   etiquetes: {len(etiq)} reconegudes de {len(noms)} textos · '
              f'{len(de_recinte)} recintes amb nom · {len(orfes)} etiquetes sense recinte')
    else:
        for r in recs:
            r.setdefault('nom', '')
            r['nom_id'] = ''
        orfes = []

    # --- els que ja hi ha al full
    vells = []
    if cami_recintes and os.path.exists(cami_recintes):
        with open(cami_recintes, encoding='utf-8-sig') as f:
            vells = list(csv.DictReader(f))
        print(f'{len(vells)} recintes al full')

    lliures = set(range(len(recs)))
    parell = {}
    for v in vells:
        try:
            cv, av = (float(v['centre_x']), float(v['centre_y'])), float(v['superficie_dwg'])
        except (KeyError, ValueError, TypeError):
            continue
        millor, dist = None, PROP_M
        for i in lliures:
            d = math.dist(recs[i]['centre'], cv)
            if d < dist and abs(recs[i]['area'] - av) / max(av, 1) < PROP_AREA:
                millor, dist = i, d
        if millor is None:      # pot haver canviat de forma: es busca pel lloc, sense l'àrea
            for i in lliures:
                d = math.dist(recs[i]['centre'], cv)
                if d < 15 and abs(recs[i]['area'] - av) / max(av, 1) < 0.5:
                    millor, dist = i, d
        if millor is not None:
            parell[v['id_recinte']] = millor
            lliures.discard(millor)

    seg = max([int(v['id_recinte'][1:]) for v in vells if v['id_recinte'][1:].isdigit()] or [0])
    for i in sorted(lliures, key=lambda i: (round(recs[i]['centre'][0]), round(recs[i]['centre'][1]))):
        seg += 1
        parell[f'R{seg:04d}'] = i

    vell_per_id = {v['id_recinte']: v for v in vells}
    files = []
    for k, i in sorted(parell.items()):
        r, v = recs[i], vell_per_id.get(k)
        if not v:
            canvi = 'NOU'
        elif abs(r['area'] - float(v['superficie_dwg'])) / max(r['area'], 1) < 0.001:
            canvi = 'IGUAL'
        else:
            canvi = 'CANVIAT'
        id_ua = (v or {}).get('id_ua', '') or r.get('id_ua', '')
        assignat = (v or {}).get('assignat_per', '')
        if not id_ua and r.get('nom_id'):
            id_ua, assignat = r['nom_id'], 'proposta'
        if r.get('duplicat'):
            id_ua, assignat = '', ''
        files.append({'id_recinte': k, 'id_ua': id_ua, 'capa_dwg': r['capa'],
                      'superficie_dwg': round(r['area'], 1), 'nom_dwg': r['nom'],
                      'assignat_per': assignat,
                      'estat': 'duplicat' if r.get('duplicat') else 'vigent',
                      'vist_a': os.path.basename(entrada),
                      'nota': ('el DWG el dibuixa dues vegades' if r.get('duplicat')
                               else (v or {}).get('nota', '')),
                      'centre_x': round(r['centre'][0], 2), 'centre_y': round(r['centre'][1], 2),
                      'canvi': canvi})
    for v in vells:
        if v['id_recinte'] not in parell:
            v = dict(v); v['estat'] = 'retirat'; v['canvi'] = 'DESAPAREGUT'
            files.append(v)

    cols = ['id_recinte', 'id_ua', 'capa_dwg', 'superficie_dwg', 'nom_dwg', 'assignat_per',
            'estat', 'vist_a', 'nota', 'centre_x', 'centre_y', 'canvi']
    cami = os.path.join(dir_sortida, 'recintes.csv')
    with open(cami, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader(); w.writerows(files)
    compte = collections.Counter(x['canvi'] for x in files)
    print('   ' + ' · '.join(f'{k}: {v}' for k, v in compte.most_common()))
    revisar = sum(v for k, v in compte.items() if k != 'IGUAL')
    print(f'   -> {cami} ({revisar} files per revisar)')

    # --- el GeoJSON net, en graus
    tr_g = Transformer.from_crs(CADASTRE, WGS84, always_xy=True)
    feats = []
    for k, i in sorted(parell.items()):
        r = recs[i]
        an = [list(tr_g.transform(x, y)) for x, y in r['pts']]
        an.append(an[0])
        feats.append({'type': 'Feature', 'id': k,
                      'properties': {'id_recinte': k, 'capa_dwg': r['capa'],
                                     'classificacio': r['cls'],
                                     'superficie_dwg': round(r['area'], 1),
                                     'nom_dwg': r['nom'],
                                     'id_ua': next((x['id_ua'] for x in files
                                                    if x['id_recinte'] == k), '')},
                      'geometry': {'type': 'Polygon', 'coordinates': [an]}})
    cami = os.path.join(dir_sortida, 'recintes.geojson')
    json.dump({'type': 'FeatureCollection',
               'name': "Recintes de les unitats d'actuació del POUPE d'Encamp",
               'crs': {'type': 'name', 'properties': {'name': 'urn:ogc:def:crs:OGC:1.3:CRS84'}},
               'features': feats}, open(cami, 'w', encoding='utf-8'), ensure_ascii=False)
    print(f'   -> {cami}')

    # --- les etiquetes, per poder-les veure allà on el delineant les va escriure
    tr_e = Transformer.from_crs(CADASTRE, WEB, always_xy=True)
    lloc = {}
    for e in etiq:
        x, y = tr_e.transform(e['x'], e['y'])
        lloc.setdefault(e['id'], []).append([round(x, 1), round(y, 1)])
    cami = os.path.join(dir_sortida, 'etiquetes.json')
    json.dump(lloc, open(cami, 'w'), separators=(',', ':'))
    print(f'   -> {cami} ({len(lloc)} unitats amb etiqueta al plànol)')

    # --- la geometria per al navegador: Web Mercator, simplificada i en deltes
    tr_w = Transformer.from_crs(CADASTRE, WEB, always_xy=True)
    proj = {k: [tr_w.transform(x, y) for x, y in recs[i]['pts']] for k, i in parell.items()}
    xs = [q[0] for v in proj.values() for q in v]
    ys = [q[1] for v in proj.values() for q in v]
    ox, oy = math.floor(min(xs)), math.floor(min(ys))
    geom = {k: a for k, a in ((k, comprimeix(v, ox, oy)) for k, v in proj.items()) if a}
    cami = os.path.join(dir_sortida, 'geometria.json')
    json.dump({'o': [ox, oy], 'r': geom}, open(cami, 'w'), separators=(',', ':'))
    print(f'   -> {cami} ({len(geom)} recintes, {round(os.path.getsize(cami) / 1024)} KB)')


def _sembla_geojson(cami):
    with open(cami, encoding='utf-8', errors='ignore') as f:
        return 'FeatureCollection' in f.read(4000)


if __name__ == '__main__':
    if len(sys.argv) not in (3, 4, 5):
        sys.exit(__doc__)
    main(*sys.argv[1:])

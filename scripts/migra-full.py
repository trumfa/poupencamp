# -*- coding: utf-8 -*-
"""Del full d'ara (27 pestanyes) al full nou (19).

No reescriu cap dada a mà: llegeix el full d'avui i en munta el nou. Es pot tornar a
executar tantes vegades com calgui, i mentre no s'importi el resultat a Google Sheets
no toca res del que hi ha en marxa.

    python scripts/migra-full.py poupe_full.json contingut.xlsx recintes.csv sortida/

  poupe_full.json   les pestanyes de la base de dades exportades a JSON
  contingut.xlsx    el llibre amb les pestanyes de contingut
  recintes.csv      la taula de recintes que surt de scripts/planol-nou.py
  sortida/          on s'escriuen els CSV i el POUPE_full_nou.xlsx

El que fa, en una frase per pestanya:

  documents   agrupa les fitxes per pàgina de BOPA: dues fitxes a la mateixa pàgina
              són, per definició, dues fitxes al mateix full publicat
  fitxes      fusiona Fitxes + Parametres + Planols, que eren 1:1, i hi posa la
              classificació que toca quan la fitxa no la diu
  unitats     es queda amb la identitat i tira les columnes que resumien un conjunt
              de fitxes (classificacio_vigent, superficie_vigent, volums, versions)
  articles    Normativa + Normativa_apartats, una fila per apartat
  claus       claus_public ja ho portava tot: Claus i Claus_subdivisions hi sobraven
"""
import json, csv, sys, os, re, collections, unicodedata

# Noms que al DWG s'escriuen diferent que a les fitxes. Vivien dins de dwg-a-mapa.py
# i el seu lloc és la columna «alies» de la pestanya unitats.
ALIES = {'ESSO': 'E.S. Esso', 'FIGUEREDO': 'E.S. Figueredo',
         'MOBIL': 'E.S. Mobil', 'ARAJOL': 'E.S. Arajol'}

VOLUM_SNU = 'VII'          # el volum VII és, per definició, sòl no urbanitzable


def llegeix_xlsx(cami):
    import openpyxl
    wb = openpyxl.load_workbook(cami, data_only=True)
    fulls = {}
    for nom in wb.sheetnames:
        ws = wb[nom]
        caps = [c.value for c in ws[1]]
        files = []
        for fila in ws.iter_rows(min_row=2, values_only=True):
            if not any(x is not None for x in fila):
                continue
            files.append({k: ('' if v is None else str(v).strip())
                          for k, v in zip(caps, fila) if k})
        fulls[nom] = files
    return fulls


def escriu(dir_sortida, nom, cols, files):
    cami = os.path.join(dir_sortida, nom + '.csv')
    with open(cami, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        for r in files:
            w.writerow({c: r.get(c, '') for c in cols})
    print(f'   {nom:<20} {len(files):>5} files · {len(cols)} columnes')
    return cols, files


def main(cami_json, cami_xlsx, cami_recintes, dir_sortida):
    os.makedirs(dir_sortida, exist_ok=True)
    F = json.load(open(cami_json, encoding='utf-8'))
    C = llegeix_xlsx(cami_xlsx)
    print('llegit el full d\'ara\n')
    taules = {}

    # ---------------------------------------------------------------- documents
    # La pàgina del BOPA és el full publicat. Coincideix exactament amb les 39
    # fitxes que la columna «compartit» d'ara marcava com a compartides.
    par = {r['id_fitxa']: r for r in F['Parametres']}
    grups = collections.OrderedDict()
    for f in sorted(F['Fitxes'], key=lambda r: (r['bopa_num'] or '', r['bopa_pagina'] or '',
                                                r['id_fitxa'])):
        # sense pàgina de BOPA no hi ha res que agrupi: cada fitxa fa document a part,
        # i la clau que ho separa no s'ha de veure a la columna bopa_pagina
        k = ('pag', f['bopa_num'], f['bopa_pagina']) if f['bopa_pagina'] else ('fitxa', f['id_fitxa'])
        grups.setdefault(k, []).append(f)

    docs, doc_de = [], {}
    for i, (k, fs) in enumerate(grups.items(), 1):
        num = k[1] if k[0] == 'pag' else fs[0]['bopa_num']
        pag = k[2] if k[0] == 'pag' else ''
        idd = f'DOC{i:04d}'
        estat = 'no separada' if any(
            par.get(f['id_fitxa'], {}).get('compartit') == 'COMPARTIT NO SEPARAT' for f in fs) \
            else ('separada' if len(fs) > 1 else 'única')
        un = lambda camp: '; '.join(sorted({f[camp] for f in fs if f.get(camp)}))
        docs.append({'id_document': idd, 'bopa_num': num,
                     'bopa_data': un('bopa_data'), 'bopa_pagina': pag if pag else '',
                     'volum': un('volum'), 'modificacio': un('modificacio'),
                     'fase_aprovacio': un('fase_aprovacio'), 'n_fitxes': len(fs),
                     'extraccio_estat': estat, 'notes': ''})
        for f in fs:
            doc_de[f['id_fitxa']] = idd
    taules['documents'] = escriu(dir_sortida, 'documents',
        ['id_document', 'bopa_num', 'bopa_data', 'bopa_pagina', 'volum', 'modificacio',
         'fase_aprovacio', 'n_fitxes', 'extraccio_estat', 'notes'], docs)
    print(f'      (dels quals {sum(1 for d in docs if d["n_fitxes"] > 1)} porten més d\'una fitxa)')

    # ---------------------------------------------------------------- unitats
    # A la pestanya UA hi ha unitats amb una fila per volum. Es queda la urbana.
    ua_rows = {}
    for u in F['UA']:
        idu = (u['id_ua'] or '').strip()
        if not idu or not (u['nom_oficial'] or '').strip():
            continue
        if idu not in ua_rows or (ua_rows[idu]['volums'] == VOLUM_SNU and u['volums'] != VOLUM_SNU):
            ua_rows[idu] = u
    pub = {r['id_ua']: r for r in C.get('ua_public', [])}
    unitats = []
    for idu, u in ua_rows.items():
        p = pub.get(idu, {})
        unitats.append({
            'id_ua': idu, 'nom_oficial': u['nom_oficial'],
            'nom_public': p.get('nom_public', ''), 'alies': ALIES.get(idu, ''),
            'resum_que_es': p.get('resum_que_es', ''),
            'resum_que_shi_pot_fer': p.get('resum_que_shi_pot_fer', ''),
            'resum_com_es_desenvolupa': p.get('resum_com_es_desenvolupa', ''),
            'avis_propi': p.get('avis_propi', ''), 'notes': '',
            'estat': 'vigent', 'substituida_per': '',
            'visible': p.get('publicat') or 'SÍ'})
    unitats.sort(key=lambda r: r['nom_oficial'].lower())
    taules['unitats'] = escriu(dir_sortida, 'unitats',
        ['id_ua', 'nom_oficial', 'nom_public', 'alies', 'resum_que_es',
         'resum_que_shi_pot_fer', 'resum_com_es_desenvolupa', 'avis_propi', 'notes',
         'estat', 'substituida_per', 'visible'], unitats)

    # ---------------------------------------------------------------- fitxes
    planol = {r['id_fitxa']: r.get('drive_id_imatge', '') for r in F.get('Planols', [])}
    cls_ua = {idu: u['classificacio_vigent'] for idu, u in ua_rows.items()}
    # per volum, quan la fila de la pestanya UA era d'un sol volum
    cls_vol = {}
    for u in F['UA']:
        vols = (u['volums'] or '').replace(';', ' ').split()
        if len(vols) == 1:
            cls_vol.setdefault((u['id_ua'], vols[0]), u['classificacio_vigent'])

    data_doc = {d['id_document']: d['bopa_data'] for d in docs}
    vigent_de = {}
    for f in F['Fitxes']:
        if f['vigent'] == 'SÍ':
            vigent_de[(f['id_ua'], f['volum'])] = f['id_fitxa']

    # Els volums sencers del pla (Volum I, II, IX…) surten a la pestanya Fitxes com si
    # fossin unitats, amb una fila a UA sense nom. No ho són: són documents normatius i
    # no tenen unitat. Es queden a fitxes, amb id_ua buit.
    fitxes = []
    for f in sorted(F['Fitxes'], key=lambda r: (r['id_ua'], r['volum'], r['modificacio'])):
        p = par.get(f['id_fitxa'], {})
        if f['id_ua'] not in ua_rows:
            f = dict(f, id_ua='')
        idd = doc_de[f['id_fitxa']]
        subst = '' if f['vigent'] == 'SÍ' else vigent_de.get((f['id_ua'], f['volum']), '')
        cls = (p.get('classificacio') or cls_vol.get((f['id_ua'], f['volum']))
               or ('SNUBLE' if f['volum'] == VOLUM_SNU else cls_ua.get(f['id_ua'], '')))
        fitxes.append({
            'id_fitxa': f['id_fitxa'], 'id_ua': f['id_ua'], 'id_document': idd,
            'volum': f['volum'], 'modificacio': f['modificacio'], 'vigent': f['vigent'],
            'substituida_per': subst,
            'vigent_des_de': data_doc.get(idd, '') if f['vigent'] == 'SÍ' else '',
            'vigent_fins_a': data_doc.get(doc_de.get(subst, ''), '') if subst else '',
            'tipus_fitxa': p.get('tipus_fitxa') or f['tipus_fitxa'],
            'classificacio': cls,
            'superficie_m2': p.get('superficie_m2', ''),
            'zones': p.get('zones', ''), 'subzones': p.get('subzones', ''),
            'alcades': p.get('alcades', ''), 'ordenacio': p.get('ordenacio', ''),
            'usos': p.get('usos', ''), 'gestio': p.get('gestio', ''),
            'descripcio': p.get('descripcio', ''), 'cobertura': p.get('cobertura', ''),
            'edificabilitat_max_m2': p.get('edificabilitat_max_m2', ''),
            'sistema_ordenacio': p.get('sistema_ordenacio', ''),
            'parcela_minima_m2': p.get('parcela_minima_m2', ''),
            'front_minim_m': p.get('front_minim_m', ''),
            'pdf_drive_id': f['drive_id'], 'pdf_fitxer': f['nom_fitxer'],
            'planol_drive_id': planol.get(f['id_fitxa'], ''),
            'revisar': f.get('revisar') or p.get('revisar', '')})
    taules['fitxes'] = escriu(dir_sortida, 'fitxes',
        ['id_fitxa', 'id_ua', 'id_document', 'volum', 'modificacio', 'vigent',
         'substituida_per', 'vigent_des_de', 'vigent_fins_a', 'tipus_fitxa',
         'classificacio', 'superficie_m2', 'zones', 'subzones', 'alcades', 'ordenacio',
         'usos', 'gestio', 'descripcio', 'cobertura', 'edificabilitat_max_m2',
         'sistema_ordenacio', 'parcela_minima_m2', 'front_minim_m', 'pdf_drive_id',
         'pdf_fitxer', 'planol_drive_id', 'revisar'], fitxes)
    amb_cls = sum(1 for r in fitxes if r['classificacio'])
    print(f'      ({amb_cls} amb classificació · {len(fitxes) - amb_cls} sense)')

    # ---------------------------------------------------------------- recintes
    recintes = []
    if os.path.exists(cami_recintes):
        with open(cami_recintes, encoding='utf-8-sig') as f:
            recintes = list(csv.DictReader(f))
    taules['recintes'] = escriu(dir_sortida, 'recintes',
        ['id_recinte', 'id_ua', 'capa_dwg', 'superficie_dwg', 'nom_dwg', 'assignat_per',
         'estat', 'vist_a', 'nota', 'centre_x', 'centre_y'], recintes)

    # ------------------------------------------------- articles i els seus apartats
    # Tres pestanyes deien el mateix dels mateixos 88 articles: Normativa, fonts i el
    # títol repetit a cada apartat de Normativa_apartats. Es queden dues, i cadascuna
    # a la seva mida: l'article, i l'apartat.
    fo = {r['id_font']: r for r in C.get('fonts', [])}
    url = {r['article']: r.get('url', '') for r in F.get('Normativa', [])}
    per_art = {}
    for r in F['Normativa_apartats']:
        per_art.setdefault(r['article'], r)
    arts = []
    for f in sorted(fo.values(), key=lambda r: int(re.search(r'(\d+)', r['article']).group(1))):
        a = per_art.get(f['article'], {})
        arts.append({'article': f['article'], 'titol': f['titol'] or a.get('titol_article', ''),
                     'document': f['document'], 'etiqueta_curta': f['etiqueta_curta'],
                     'font': a.get('font', ''), 'bopa': f['bopa'] or a.get('bopa', ''),
                     'url': f['url_directa'] or f['url_oficial'] or url.get(f['article'], ''),
                     'verificat': f.get('verificat', 'NO')})
    taules['articles'] = escriu(dir_sortida, 'articles',
        ['article', 'titol', 'document', 'etiqueta_curta', 'font', 'bopa', 'url',
         'verificat'], arts)

    aps = [{'id_apartat': r['id'], 'article': r['article'], 'apartat': r['apartat'],
            'text': r['text'], 'tema': r['tema'], 'abast': r['abast'],
            'claus_aplicables': r.get('claus_aplicables', '')}
           for r in F['Normativa_apartats']]
    taules['apartats'] = escriu(dir_sortida, 'apartats',
        ['id_apartat', 'article', 'apartat', 'text', 'tema', 'abast', 'claus_aplicables'],
        aps)

    # ---------------------------------------------------------------- claus
    claus = [{'clau': r['clau'], 'clau_mare': r.get('clau_mare', ''), 'tipus': r['tipus'],
              'naturalesa': r.get('naturalesa', ''),
              'denominacio_oficial': r.get('denominacio_oficial', ''),
              'article': r.get('article', ''),
              'coef_edificabilitat': r.get('coef_edificabilitat', ''),
              'font': r.get('font', ''), 'nom_public': r.get('nom_public', ''),
              'frase_planera': r.get('frase_planera', ''),
              'visible': r.get('visible', 'SÍ'), 'revisat': r.get('revisat', 'NO')}
             for r in C['claus_public']]
    taules['claus'] = escriu(dir_sortida, 'claus',
        ['clau', 'clau_mare', 'tipus', 'naturalesa', 'denominacio_oficial', 'article',
         'coef_edificabilitat', 'font', 'nom_public', 'frase_planera', 'visible',
         'revisat'], claus)

    # ------------------------------------------------------- claus_parametres
    # valors_public ja porta les columnes de l'extracció i les teves; el que hi falta
    # són les files de la clau 11 sense lletra, que 11A i 11B han substituït.
    noms_par = {(r['clau'], r['article'], r['lletra']): r['parametre']
                for r in F['Claus_parametres']}
    vals = []
    for r in C['valors_public']:
        k = (r['clau'], r['article'], r['lletra'])
        mare = next((c['clau_mare'] for c in claus if c['clau'] == r['clau']), '')
        vals.append({'id_valor': r['id_valor'], 'clau': r['clau'],
                     'parametre': noms_par.get(k) or noms_par.get((mare, r['article'], r['lletra']), ''),
                     'parametre_bd': r['parametre_bd'], 'article': r['article'],
                     'lletra': r['lletra'], 'valor_original': r['valor_original'],
                     'valor_numeric': r['valor_numeric'], 'unitat': r['unitat'],
                     'remet_a': r['remet_a'], 'text_planer': r['text_planer'],
                     'valor_destacat': r['valor_destacat'],
                     'visible': r['visible'], 'revisat': r['revisat']})
    taules['claus_parametres'] = escriu(dir_sortida, 'claus_parametres',
        ['id_valor', 'clau', 'parametre', 'parametre_bd', 'article', 'lletra',
         'valor_original', 'valor_numeric', 'unitat', 'remet_a', 'text_planer',
         'valor_destacat', 'visible', 'revisat'], vals)
    sense = sum(1 for v in vals if not v['parametre'])
    if sense:
        print(f'      ({sense} sense nom de paràmetre: no eren a Claus_parametres)')

    # ---------------------------------------------------------------- proteccions
    prot = [dict(r, id_proteccio=f'PROT{i:04d}') for i, r in enumerate(F['Proteccions'], 1)]
    taules['proteccions'] = escriu(dir_sortida, 'proteccions',
        ['id_proteccio', 'nom', 'nivell', 'categoria', 'tipus', 'adreca', 'id_ua',
         'obligacio', 'article', 'font', 'bopa'], prot)

    # ---------------------------------------------------------------- la resta
    taules['regles_calcul'] = escriu(dir_sortida, 'regles_calcul',
        ['id_regla', 'nom', 'condicio_aplicacio', 'formula', 'unitat', 'article',
         'estat', 'observacions'], F.get('Regles_calcul', []))
    taules['cadastre'] = escriu(dir_sortida, 'cadastre',
        ['referencia', 'id_ua', 'adreca', 'font'], [])
    taules['config'] = escriu(dir_sortida, 'config', ['clau', 'valor', 'notes'], C['config'])
    taules['textos'] = escriu(dir_sortida, 'textos',
        ['id_text', 'ubicacio', 'text_ca'], C['textos_web'])
    taules['blocs'] = escriu(dir_sortida, 'blocs',
        ['id_bloc', 'ordre', 'titol_public', 'subtitol', 'icona', 'condicio', 'visible'],
        C['blocs'])
    taules['parametres'] = escriu(dir_sortida, 'parametres',
        ['parametre_bd', 'id_bloc', 'ordre', 'etiqueta_publica', 'ajuda_curta', 'visible'],
        C['parametres_public'])
    taules['avisos'] = escriu(dir_sortida, 'avisos',
        ['id_avis', 'condicio', 'to', 'text', 'visible'], C['avisos'])
    taules['glossari'] = escriu(dir_sortida, 'glossari',
        ['terme', 'definicio_planera', 'definicio_normativa', 'font', 'article',
         'veure_tambe', 'visible'], C['glossari_public'])
    taules['capes'] = escriu(dir_sortida, 'capes',
        ['id_capa', 'nom_public', 'fitxer', 'ordre', 'color', 'per_defecte', 'clicable',
         'font', 'visible'],
        [{'id_capa': 'unitats', 'nom_public': "Unitats d'actuació",
          'fitxer': 'data/recintes.geojson', 'ordre': '10', 'color': '',
          'per_defecte': 'SÍ', 'clicable': 'SÍ',
          'font': 'DWG cadastral, capes 01 1 a 01 11', 'visible': 'SÍ'}])

    import datetime
    taules['canvis'] = escriu(dir_sortida, 'canvis',
        ['data', 'tipus', 'que', 'bopa', 'qui', 'notes'],
        [{'data': datetime.date.today().strftime('%d/%m/%Y'), 'tipus': 'correcció',
          'que': 'Reestructuració del full: de 27 pestanyes a 19',
          'bopa': '', 'qui': '', 'notes': 'Cap dada canviada; només com està organitzada.'}])

    # ---------------------------------------------------------------- el llibre
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    wb = Workbook()
    wb.remove(wb.active)
    ORDRE = ['documents', 'fitxes', 'unitats', 'recintes', 'articles', 'apartats',
             'claus', 'claus_parametres', 'proteccions', 'regles_calcul', 'cadastre',
             'config', 'textos', 'blocs', 'parametres', 'avisos', 'glossari',
             'capes', 'canvis']
    for nom in ORDRE:
        cols, files = taules[nom]
        ws = wb.create_sheet(nom)
        ws.append(cols)
        for r in files:
            ws.append([r.get(c, '') for c in cols])
        for c in ws[1]:
            c.font = Font(bold=True, color='FFFFFF')
            c.fill = PatternFill('solid', fgColor='1F5C4A')
            c.alignment = Alignment(vertical='center')
        ws.freeze_panes = 'A2'
        for i, c in enumerate(cols):
            ws.column_dimensions[ws.cell(row=1, column=i + 1).column_letter].width = \
                min(max(12, len(c) + 4), 42)
    cami = os.path.join(dir_sortida, 'POUPE_full_nou.xlsx')
    wb.save(cami)
    print(f'\n{len(ORDRE)} pestanyes -> {cami}')


if __name__ == '__main__':
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    main(*sys.argv[1:])

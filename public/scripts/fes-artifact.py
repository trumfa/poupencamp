# -*- coding: utf-8 -*-
"""public/index.html -> una sola pàgina que es val per ella mateixa

    python scripts/fes-artifact.py sortida.html

L'artifact és una sola pàgina que ha de valer-se per ella mateixa: no pot anar a
buscar data.json, ni les tessel·les del mapa, ni els plànols de les fitxes. Per
això les dades s'hi incrusten i el fons del plànol arrenca apagat.
"""
import os, sys

ARREL = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..') + os.sep
SORTIDA = sys.argv[1] if len(sys.argv) > 1 else ARREL + 'poupe-artifact.html'

ESQUEMA = 'https://claude.ai/code/artifact/3d0a9d73-64e9-451e-85bd-8450f4537f6f'

s = open(ARREL + 'public/index.html', encoding='utf-8').read()
dades = open(ARREL + 'public/data.json', encoding='utf-8').read()

# 1. treure l'embolcall: l'artifact hi posa el seu
i = s.index('<title>'); j = s.index('</head>')
k = s.index('<body>') + len('<body>'); l = s.rindex('</body>')
s = s[i:j].rstrip() + '\n' + s[k:l].rstrip() + '\n'

# 2. les dades, a dins
assert '__DADES__' in s, 'no hi ha el forat de les dades'
s = s.replace('__DADES__', dades.replace('</', '<\\/'), 1)

# 3. els enllaços interns cap als altres artifacts
s = s.replace('href="esquema.html"', f'href="{ESQUEMA}" target="_blank" rel="noopener"')

# 4. el fons del mapa: aquí les tessel·les no carreguen
s = s.replace("localStorage.getItem('poupe-fons') || 'orto'",
              "localStorage.getItem('poupe-fons') || 'cap'", 1)

open(SORTIDA, 'w', encoding='utf-8').write(s)
print(f'{SORTIDA} · {len(s)/1024:.0f} KB')

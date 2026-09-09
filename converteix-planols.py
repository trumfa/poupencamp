# -*- coding: utf-8 -*-
"""Converteix els plànols PNG del Drive a WebP per al repositori.

Com fer-ho servir a Google Colab (la via més curta, perquè els fitxers ja són al Drive):

    from google.colab import drive
    drive.mount('/content/drive')
    !pip -q install pillow
    !python converteix-planols.py \
        --entrada "/content/drive/MyDrive/.../Planols_POUPE" \
        --sortida "/content/planols_webp"

I després es baixa la carpeta de sortida i es copia a public/planols/ del repositori.

El nom del fitxer és l'identificador de la fitxa (per exemple TREMAT__III__M04.png),
que és exactament el que la web busca: public/planols/TREMAT__III__M04.webp
"""
import argparse, os, sys

try:
    from PIL import Image
except ImportError:
    sys.exit("Falta Pillow. Instal·la'l amb: pip install pillow")

ap = argparse.ArgumentParser()
ap.add_argument('--entrada', required=True, help='Carpeta amb els PNG originals')
ap.add_argument('--sortida', required=True, help='Carpeta on deixar els WebP')
ap.add_argument('--ample', type=int, default=1600, help='Amplada màxima en píxels (per defecte 1600)')
ap.add_argument('--qualitat', type=int, default=80, help='Qualitat WebP 1-100 (per defecte 80)')
args = ap.parse_args()

os.makedirs(args.sortida, exist_ok=True)
originals = [f for f in sorted(os.listdir(args.entrada)) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
if not originals:
    sys.exit(f"No hi ha imatges a {args.entrada}")

pes_abans = pes_despres = 0
for i, nom in enumerate(originals, 1):
    org = os.path.join(args.entrada, nom)
    desti = os.path.join(args.sortida, os.path.splitext(nom)[0] + '.webp')
    with Image.open(org) as im:
        im = im.convert('RGB')
        if im.width > args.ample:
            im = im.resize((args.ample, round(im.height * args.ample / im.width)), Image.LANCZOS)
        im.save(desti, 'WEBP', quality=args.qualitat, method=6)
    pes_abans += os.path.getsize(org)
    pes_despres += os.path.getsize(desti)
    if i % 25 == 0 or i == len(originals):
        print(f"  {i}/{len(originals)}")

mb = lambda b: round(b / 1048576, 1)
print(f"\n{len(originals)} plànols · {mb(pes_abans)} MB -> {mb(pes_despres)} MB "
      f"({round(100 - pes_despres / pes_abans * 100)}% menys)")
print(f"Copia el contingut de {args.sortida} a public/planols/ del repositori.")

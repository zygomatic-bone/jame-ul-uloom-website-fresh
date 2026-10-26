"""Builds the self-hosted web fonts in tools/portal-ui/fonts/ (run only when the fonts change; the output is committed).

  python3 tools/make_fonts.py <Inter OTF folder> <Lora-Variable.ttf>

* Inter 4.0 (SIL OFL 1.1, no Reserved Font Name): Regular, SemiBold and Bold, cut down to the Latin characters this site uses.
* Lora 3.0 (SIL OFL 1.1, Reserved Font Name "Lora"): the variable font (weights 400-700), cut down the same way. The OFL does not allow a
  modified version to keep the reserved name, so the cut-down file is renamed "Jamia Serif" (see portal-ui/fonts/NOTICE.txt).
Output is WOFF (zlib), which every current browser reads; it needs no extra tools to build (WOFF2 would need the brotli module).
Needs: fontTools (pip install fonttools).
"""
import sys
from pathlib import Path
from fontTools import subset
from fontTools.ttLib import TTFont

OUT = Path(__file__).resolve().parent / 'portal-ui' / 'fonts'
# Basic Latin, Latin-1, Latin Extended-A (macron letters such as ā ī ū), the dotted letters used to transliterate Arabic names
# (Ḍ ḍ Ḥ ḥ Ṣ ṣ Ṭ ṭ Ẓ ẓ) and the modifier letters ʾ ʿ, general punctuation, currency, the arrows the site uses, minus and multiplication signs.
UNICODES = ([*range(0x20, 0x7F), *range(0xA0, 0x180), 0x2BE, 0x2BF, *range(0x2010, 0x2028), *range(0x2030, 0x203B),
             0x1E0C, 0x1E0D, 0x1E24, 0x1E25, 0x1E62, 0x1E63, 0x1E6C, 0x1E6D, 0x1E92, 0x1E93,
             0x2044, 0x20AC, 0x20B9, 0x2122, 0x2190, 0x2191, 0x2192, 0x2193, 0x2197, 0x2212, 0x00D7, 0x2022, 0xFEFF])
FEATURES = ['kern', 'liga', 'ccmp', 'locl', 'mark', 'mkmk', 'tnum', 'case']

def cut(src: Path, dst: Path, rename: str | None = None):
    opts = subset.Options()
    opts.flavor = 'woff'
    opts.layout_features = FEATURES
    opts.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14, 16, 17]
    opts.notdef_outline = True
    opts.hinting = False
    font = TTFont(str(src))
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=UNICODES)
    sub.subset(font)
    if rename:   # OFL: a modified version must not use the Reserved Font Name
        nm = font['name']
        for rec in list(nm.names):
            if rec.nameID in (1, 16):
                nm.setName(rename, rec.nameID, rec.platformID, rec.platEncID, rec.langID)
            elif rec.nameID == 4:
                nm.setName(rename + ' Variable', 4, rec.platformID, rec.platEncID, rec.langID)
            elif rec.nameID == 6:
                nm.setName(rename.replace(' ', '') + '-Variable', 6, rec.platformID, rec.platEncID, rec.langID)
    font.flavor = 'woff'
    font.save(str(dst))
    print(f'{dst.name}: {dst.stat().st_size:,} bytes')

if __name__ == '__main__':
    inter_dir, lora = Path(sys.argv[1]), Path(sys.argv[2])
    OUT.mkdir(exist_ok=True)
    for weight in ('Regular', 'SemiBold', 'Bold'):
        cut(inter_dir / f'Inter-{weight}.otf', OUT / f'Inter-{weight}.woff')
    cut(lora, OUT / 'JamiaSerif-Variable.woff', rename='Jamia Serif')

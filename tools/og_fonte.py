"""Gera lib/og_fonte.js: glifos da fonte Inter (licença SIL OFL) já rasterizados, para a Function
que desenha o cartão de prévia (functions/og/) sem dependências nem WebAssembly.

Rodar só quando mudar tamanho, fonte ou caracteres:  python tools/og_fonte.py [pasta-da-Inter]
"""
import base64
import gzip
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PASTA = Path(sys.argv[1] if len(sys.argv) > 1 else "/usr/share/fonts/opentype/inter")
TEXTO = "".join(chr(c) for c in range(32, 127)) + "ÁÀÂÃÉÊÍÓÔÕÚÜÇáàâãéêíóôõúüçº·×–…"
# nome: (arquivo, tamanho em px, caracteres)
ESTILOS = {
    "valor": ("InterDisplay-Bold.otf", 128, "R$ 0123456789,.mibl"),
    "titulo": ("InterDisplay-Bold.otf", 72, TEXTO),
    "titulo2": ("InterDisplay-Bold.otf", 52, TEXTO),
    "corpo": ("Inter-Medium.otf", 36, TEXTO),
    "rodape": ("Inter-Regular.otf", 26, TEXTO),
}

alfa = bytearray()
saida = {}
for nome, (arq, tam, chars) in ESTILOS.items():
    fonte = ImageFont.truetype(str(PASTA / arq), tam)
    glifos = {}
    for ch in chars:
        x0, y0, x1, y1 = fonte.getbbox(ch, anchor="ls")
        w, h = max(0, x1 - x0), max(0, y1 - y0)
        if w and h:
            img = Image.new("L", (w, h), 0)
            ImageDraw.Draw(img).text((-x0, -y0), ch, font=fonte, fill=255, anchor="ls")
            dados = img.tobytes()
        else:
            dados = b""
        # [largura, altura, deslocamento x, deslocamento y (a partir da linha de base), avanço, início no bloco alfa]
        glifos[ch] = [w, h, x0, y0, round(fonte.getlength(ch), 2), len(alfa)]
        alfa += dados
    asc, desc = fonte.getmetrics()
    saida[nome] = {"tam": tam, "asc": asc, "desc": desc, "g": glifos}

b64 = base64.b64encode(gzip.compress(bytes(alfa), 9, mtime=0)).decode()
destino = Path(__file__).resolve().parent.parent / "lib" / "og_fonte.js"
destino.write_text(
    "// Gerado por tools/og_fonte.py a partir da fonte Inter (SIL Open Font License 1.1). Não editar à mão.\n"
    f"export const ESTILOS = {json.dumps(saida, ensure_ascii=False, separators=(',', ':'))};\n"
    f"export const ALFA_GZ = \"{b64}\";\n",
    encoding="utf-8",
)
print(f"{destino}: {len(alfa):,} bytes de alfa, {destino.stat().st_size:,} bytes no arquivo")

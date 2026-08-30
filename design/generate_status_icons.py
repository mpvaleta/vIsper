"""
Gera os 6 ícones da barra de menu: a SILHUETA DO MASCOTE (a mesma de
design/menubar_icon_template.svg, o briefing original) pintada nas
CORES EXATAS da paleta semântica de design/layouts_mockup.html.

Por que não é mais um círculo liso: a v1 usava emoji, e a Valeta
testou de verdade e apontou que "as cores que você falou não estão
funcionando" — emoji usa as cores do FONTE da Apple, não a paleta.
A v2 trocou por círculos sólidos nas cores certas, o que resolveu a
COR mas jogou fora a FORMA: "os ícones deveriam seguir o briefing
inicial". Esta é a v3 — cor certa E forma certa. A forma (corpo
arredondado + duas antenas + as ondas de som) é o que identifica o
vIsper na barra; a cor é o que comunica o estado. São dois canais
independentes de propósito, como o CLAUDE.md já documentava pra
marca vs. status.

Escrito com zlib + struct (biblioteca padrão) de propósito: nenhuma
dependência nova (Pillow, cairosvg etc.) só pra gerar 6 PNGs pequenos
uma vez. Como não dá pra "importar" um SVG sem dependência, as
primitivas do briefing estão transcritas em SHAPES abaixo, com os
números vindo LITERALMENTE de design/menubar_icon_template.svg —
mexeu lá, mexe aqui e rode de novo.

Os PNGs gerados vivem em status_icons/ (raiz do projeto, ao lado de
main.py — main.py resolve o caminho relativo a __file__, o que
funciona tanto rodando do código quanto de dentro do .app empacotado,
já que o py2app copia main.py pra Contents/Resources/ e leva
status_icons/ junto via DATA_FILES em setup.py) e são COMMITADOS como
asset estático — main.py só referencia o caminho, nunca gera nada em
runtime. Rode de novo se a paleta ou o desenho mudarem:

    python3 design/generate_status_icons.py
"""
import struct
import zlib

# 88px dá margem de sobra: o rumps fixa a NSImage em 20x20 PONTOS
# (rumps.py, _nsimage_from_file -> image.setSize_((20, 20)) — conferido
# no source da 0.4.0, não de memória), então numa tela Retina 2x são
# 40px e 3x são 60px. Sobra bitmap pra reduzir com qualidade em
# qualquer uma, e o arquivo continua com menos de 1 KB.
SIZE = 88

COLORS = {
    "stopped": "#9B96A8",
    "loading": "#E0A83E",
    "listening": "#2FAE5C",
    "dictating": "#E0645A",
    "sent": "#4E7FE0",
    "error": "#B5726B",
}

# ---------------------------------------------------------------------
# O desenho, em coordenadas do viewBox 400x400 de
# design/menubar_icon_template.svg. Cada entrada é (tipo, args...,
# opacidade) — a opacidade existe só pra terceira onda de som, que no
# briefing é mais fraca que a primeira.
# ---------------------------------------------------------------------
SHAPES = [
    # antena esquerda: haste + ponta
    ("rrect", (163, 150, 11, 42, 5.5), 1.0),
    ("circle", (168.5, 148, 9), 1.0),
    # antena direita
    ("rrect", (226, 150, 11, 42, 5.5), 1.0),
    ("circle", (231.5, 148, 9), 1.0),
    # corpo
    ("rrect", (140, 188, 120, 100, 22), 1.0),
    # ondas de som saindo da direita (curva quadrática, ponta redonda)
    ("qstroke", ((285, 195), (294, 205), (285, 215), 10), 1.0),
    ("qstroke", ((300, 183), (320, 205), (300, 227), 10), 0.55),
]

PAD = 4  # px de respiro em volta do desenho, dentro do canvas


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


# ---------------------------------------------------------------------
# Distâncias com sinal (negativo = dentro). Usar distância em vez de
# "pinta/não pinta" é o que dá antialiasing de graça: a cobertura de
# cada pixel sai de quão perto ele está da borda.
# ---------------------------------------------------------------------

def _sd_rrect(px, py, x, y, w, h, r):
    cx, cy = x + w / 2.0, y + h / 2.0
    qx = abs(px - cx) - (w / 2.0 - r)
    qy = abs(py - cy) - (h / 2.0 - r)
    dx, dy = max(qx, 0.0), max(qy, 0.0)
    return (dx * dx + dy * dy) ** 0.5 + min(max(qx, qy), 0.0) - r


def _sd_circle(px, py, cx, cy, r):
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5 - r


def _quad_points(p0, p1, p2, n=48):
    """Amostra a curva quadrática — a distância exata até uma Bézier
    não tem forma fechada barata, e com 48 pontos o erro já é menor
    que o antialiasing de um pixel."""
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        pts.append(
            (
                u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1],
            )
        )
    return pts


def _sd_polyline(px, py, pts, largura):
    """Traço de ponta redonda = distância até a polilinha menos metade
    da espessura (é exatamente o que `stroke-linecap="round"` faz)."""
    melhor = float("inf")
    for i in range(len(pts) - 1):
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        vx, vy = bx - ax, by - ay
        wx, wy = px - ax, py - ay
        comp = vx * vx + vy * vy
        t = 0.0 if comp == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / comp))
        dx, dy = wx - t * vx, wy - t * vy
        d = dx * dx + dy * dy
        if d < melhor:
            melhor = d
    return melhor ** 0.5 - largura / 2.0


def _prepare():
    """Pré-calcula o que não depende do pixel: as polilinhas das ondas
    e a caixa que contém TODA a tinta."""
    preparadas = []
    minx = miny = float("inf")
    maxx = maxy = float("-inf")
    for tipo, args, opacidade in SHAPES:
        if tipo == "rrect":
            x, y, w, h, _r = args
            caixa = (x, y, x + w, y + h)
            preparadas.append((tipo, args, opacidade))
        elif tipo == "circle":
            cx, cy, r = args
            caixa = (cx - r, cy - r, cx + r, cy + r)
            preparadas.append((tipo, args, opacidade))
        else:  # qstroke
            p0, p1, p2, largura = args
            pts = _quad_points(p0, p1, p2)
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            caixa = (
                min(xs) - largura / 2,
                min(ys) - largura / 2,
                max(xs) + largura / 2,
                max(ys) + largura / 2,
            )
            preparadas.append((tipo, (pts, largura), opacidade))
        minx, miny = min(minx, caixa[0]), min(miny, caixa[1])
        maxx, maxy = max(maxx, caixa[2]), max(maxy, caixa[3])
    return preparadas, (minx, miny, maxx, maxy)


def transform(size=SIZE, pad=PAD):
    """(escala, dx, dy) pra levar coordenada do SVG pra pixel do PNG.

    Público de propósito: test_status_icons.py usa isto pra conferir
    pontos do DESENHO (dentro do corpo, no vão entre as antenas) nos
    bytes do PNG, sem repetir a conta e sem virar um teste que só
    confirma a si mesmo.
    """
    _formas, (minx, miny, maxx, maxy) = _prepare()
    largura, altura = maxx - minx, maxy - miny
    util = size - 2 * pad
    escala = min(util / largura, util / altura)
    dx = (size - largura * escala) / 2.0 - minx * escala
    dy = (size - altura * escala) / 2.0 - miny * escala
    return escala, dx, dy


def to_pixel(sx, sy, size=SIZE, pad=PAD):
    escala, dx, dy = transform(size, pad)
    return sx * escala + dx, sy * escala + dy


def mascot_rgba(size, rgb):
    """A silhueta do briefing, na cor pedida, com alpha antialiasado."""
    r, g, b = rgb
    formas, _caixa = _prepare()
    escala, dx, dy = transform(size)
    # A borda suave tem ~1px NO PNG; convertida pra unidades do SVG
    # porque é lá que as distâncias são medidas.
    suave = 1.0 / escala
    rows = []
    for y in range(size):
        row = bytearray()
        # +0.5: mede no CENTRO do pixel, senão o desenho sai meio pixel
        # deslocado pra cima e pra esquerda.
        sy = (y + 0.5 - dy) / escala
        for x in range(size):
            sx = (x + 0.5 - dx) / escala
            cobertura = 0.0
            for tipo, args, opacidade in formas:
                if tipo == "rrect":
                    d = _sd_rrect(sx, sy, *args)
                elif tipo == "circle":
                    d = _sd_circle(sx, sy, *args)
                else:
                    d = _sd_polyline(sx, sy, args[0], args[1])
                if d >= suave:
                    continue
                # Cobertura linear na faixa de transição: 1 dentro,
                # 0 fora, meio-termo em cima da borda.
                c = 1.0 if d <= -suave else (suave - d) / (2 * suave)
                # União de formas: fica a mais opaca das que cobrem
                # este pixel (somar faria a sobreposição estourar).
                cobertura = max(cobertura, c * opacidade)
                if cobertura >= 1.0:
                    break
            row += bytes((r, g, b, int(round(min(1.0, cobertura) * 255))))
        rows.append(bytes(row))
    return rows


def write_png(path, size, rows):
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8bit RGBA, no interlace
    raw = b"".join(b"\x00" + row for row in rows)  # filter type 0 per scanline
    idat = zlib.compress(raw, 9)
    with open(path, "wb") as f:
        f.write(sig)
        f.write(chunk(b"IHDR", ihdr))
        f.write(chunk(b"IDAT", idat))
        f.write(chunk(b"IEND", b""))


if __name__ == "__main__":
    import os

    out_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "status_icons"
    )
    os.makedirs(out_dir, exist_ok=True)
    for name, hexcolor in COLORS.items():
        rgb = hex_to_rgb(hexcolor)
        rows = mascot_rgba(SIZE, rgb)
        path = os.path.join(out_dir, f"{name}.png")
        write_png(path, SIZE, rows)
        print(f"{path}  ({hexcolor})")

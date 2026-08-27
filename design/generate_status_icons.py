"""
Gera os 6 ícones coloridos da barra de menu — círculos sólidos nas
CORES EXATAS da paleta semântica de design/layouts_mockup.html (a
fonte da verdade documentada no CLAUDE.md).

Escrito com zlib + struct (biblioteca padrão) de propósito: nenhuma
dependência nova (Pillow etc.) só pra gerar 6 PNGs pequenos uma vez.
Os PNGs gerados vivem em status_icons/ (raiz do projeto, ao lado de
main.py — main.py resolve o caminho relativo a __file__, o que
funciona tanto rodando do código quanto de dentro do .app empacotado,
já que o py2app copia main.py pra Contents/Resources/ e leva
status_icons/ junto via DATA_FILES em setup.py) e são COMMITADOS como
asset estático — main.py só referencia o caminho, nunca gera nada em
runtime. Rode de novo só se a paleta em design/layouts_mockup.html
mudar:

    python3 design/generate_status_icons.py
"""
import struct
import zlib

SIZE = 88  # px — dá margem de sobra pra rumps escalar pra 20pt (Retina 3x = 60px)

COLORS = {
    "stopped": "#9B96A8",
    "loading": "#E0A83E",
    "listening": "#2FAE5C",
    "dictating": "#E0645A",
    "sent": "#4E7FE0",
    "error": "#B5726B",
}


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def circle_rgba(size, rgb, pad=6):
    r, g, b = rgb
    cx = cy = (size - 1) / 2
    radius = (size - pad * 2) / 2
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            dx = x - cx
            dy = y - cy
            dist = (dx * dx + dy * dy) ** 0.5
            # Anti-serrilhado: transição suave de 1.25px na borda.
            edge = radius - dist
            if edge >= 1.25:
                alpha = 255
            elif edge <= -1.25:
                alpha = 0
            else:
                alpha = round(255 * (edge + 1.25) / 2.5)
            row += bytes((r, g, b, alpha))
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
        rows = circle_rgba(SIZE, rgb)
        path = os.path.join(out_dir, f"{name}.png")
        write_png(path, SIZE, rows)
        print(f"{path}  ({hexcolor})")

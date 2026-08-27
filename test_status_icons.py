"""
Testa os ícones da barra de menu (status_icons/*.png, gerados por
design/generate_status_icons.py) nos DOIS eixos que já deram
problema, ligando cada um à sua fonte da verdade:

- COR: "as cores que você falou não estão funcionando". A v1 usava
  emoji, e emoji tem as cores do FONTE da Apple, não as da paleta
  semântica documentada (🟠 não é terracota). Aqui o hex de
  design/layouts_mockup.html é comparado com o BYTE que está de
  verdade no PNG que o main.py carrega.
- FORMA: "os ícones deveriam seguir o briefing inicial". A v2
  consertou a cor mas virou um círculo liso, perdendo o mascote.
  Aqui pontos do desenho de design/menubar_icon_template.svg são
  levados pro pixel correspondente (pela MESMA transformação que o
  gerador usa, exposta como gen.to_pixel) e conferidos: tinta onde o
  briefing tem tinta, vazio onde o briefing tem vazio. O vão ENTRE as
  duas antenas é o teste que um círculo não passa.

Decodifica PNG com zlib + struct (biblioteca padrão) — mesma escolha
de design/generate_status_icons.py, sem dependência nova só pra ler 6
arquivos pequenos.
"""

import re
import struct
import unittest
import zlib
from pathlib import Path

import design.generate_status_icons as gen

ICON_DIR = Path(__file__).parent / "status_icons"
MOCKUP_PATH = Path(__file__).parent / "design" / "layouts_mockup.html"


def _decode_png(path: Path):
    """(largura, altura, linhas_rgba) — só o suficiente pra ler um PNG
    RGBA de 8 bits sem interlace, que é tudo que geramos aqui."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path} não é um PNG válido"
    width, height = struct.unpack(">II", data[16:24])
    idat = b""
    pos = 8
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        tag = data[pos + 4 : pos + 8]
        if tag == b"IDAT":
            idat += data[pos + 8 : pos + 8 + length]
        pos += 8 + length + 4
    raw = zlib.decompress(idat)
    stride = 1 + width * 4  # 1 byte de filtro (sempre 0 aqui) + RGBA
    rows = [raw[y * stride + 1 : y * stride + 1 + width * 4] for y in range(height)]
    return width, height, rows


def _center_pixel(path: Path):
    width, height, rows = _decode_png(path)
    row = rows[height // 2]
    i = (width // 2) * 4
    return tuple(row[i : i + 4])  # (r, g, b, a)


def _pixel_no_desenho(path: Path, sx: float, sy: float):
    """Pixel correspondente a um ponto em coordenada do SVG do
    briefing. Usa gen.to_pixel de propósito — repetir a conta aqui
    faria o teste passar mesmo se a transformação estivesse errada."""
    _w, _h, rows = _decode_png(path)
    px, py = gen.to_pixel(sx, sy)
    x, y = int(px), int(py)
    return tuple(rows[y][x * 4 : x * 4 + 4])


def _mockup_colors():
    """Lê os hex de design/layouts_mockup.html direto — a fonte da
    verdade que o CLAUDE.md documenta. Regex simples: as variáveis já
    são `--status-x: #RRGGBB;` numa linha só."""
    texto = MOCKUP_PATH.read_text(encoding="utf-8")
    pares = re.findall(r"--status-(\w[\w-]*):\s*(#[0-9A-Fa-f]{6});", texto)
    return {nome: valor.upper() for nome, valor in pares}


class CoresBatemComOMockupTest(unittest.TestCase):
    def test_generator_usa_os_mesmos_hex_do_mockup(self):
        mockup = _mockup_colors()
        # Nomes não são idênticos 1:1 (o generator usa os nomes de
        # ESTADO do app — "stopped", "dictating" — o mockup usa os da
        # UI — "idle", "dictate"); o que importa é que cada VALOR hex
        # usado pelo generator apareça em algum lugar do mockup.
        hex_do_mockup = set(mockup.values())
        for estado, hexcolor in gen.COLORS.items():
            with self.subTest(estado=estado):
                self.assertIn(
                    hexcolor.upper(),
                    hex_do_mockup,
                    f"{estado}={hexcolor} não é nenhuma cor de "
                    f"design/layouts_mockup.html — a paleta divergiu",
                )


class PngsCorrespondemAsCoresTest(unittest.TestCase):
    def test_todo_png_existe_e_e_rgba(self):
        for estado in gen.COLORS:
            with self.subTest(estado=estado):
                caminho = ICON_DIR / f"{estado}.png"
                self.assertTrue(caminho.is_file(), f"{caminho} não existe")
                width, height, rows = _decode_png(caminho)
                self.assertEqual(width, gen.SIZE)
                self.assertEqual(height, gen.SIZE)
                self.assertEqual(len(rows[0]), width * 4)  # 4 canais = RGBA

    def test_pixel_central_e_a_cor_exata_documentada(self):
        for estado, hexcolor in gen.COLORS.items():
            with self.subTest(estado=estado):
                r, g, b, a = _center_pixel(ICON_DIR / f"{estado}.png")
                self.assertEqual((r, g, b), gen.hex_to_rgb(hexcolor))
                # O centro do canvas cai dentro do CORPO do mascote,
                # que é sólido — então aqui a cor sai pura, sem
                # antialiasing misturando nada.
                self.assertEqual(a, 255)

    def test_cantos_sao_transparentes(self):
        # O ícone é uma silhueta, não um quadrado colorido: o canto do
        # canvas fica fora de qualquer forma do briefing.
        for estado in gen.COLORS:
            with self.subTest(estado=estado):
                _w, _h, rows = _decode_png(ICON_DIR / f"{estado}.png")
                canto = rows[0][0:4]
                self.assertEqual(canto[3], 0, "canto do PNG devia ser transparente")


class FormaSegueOBriefingTest(unittest.TestCase):
    """Pontos escolhidos a dedo em design/menubar_icon_template.svg.

    Um por peça do desenho, mais o vão entre as antenas — que é
    justamente onde um círculo (a v2) teria tinta e o mascote não tem.
    """

    ICONE = ICON_DIR / "listening.png"

    def test_tem_tinta_onde_o_briefing_tem_tinta(self):
        pontos = {
            "corpo (centro)": (200, 238),
            "haste da antena esquerda": (168.5, 170),
            "ponta da antena esquerda": (168.5, 148),
            "haste da antena direita": (231.5, 170),
            "ponta da antena direita": (231.5, 148),
            "primeira onda de som": (285, 195),
        }
        for nome, (sx, sy) in pontos.items():
            with self.subTest(peca=nome):
                _r, _g, _b, a = _pixel_no_desenho(self.ICONE, sx, sy)
                self.assertGreater(a, 200, f"{nome} sumiu do ícone")

    def test_vao_entre_as_antenas_fica_vazio(self):
        # (200, 160) está no meio das duas antenas, acima do corpo:
        # tinta aqui quer dizer que a silhueta virou um borrão (ou um
        # círculo de novo) e o mascote não se reconhece mais.
        _r, _g, _b, a = _pixel_no_desenho(self.ICONE, 200, 160)
        self.assertEqual(a, 0, "o vão entre as antenas devia ser transparente")

    def test_a_onda_mais_distante_e_mais_fraca(self):
        # O briefing desenha a segunda onda com opacity 0.55 — é o que
        # dá a sensação de som se afastando. Se as duas saírem com a
        # mesma força, o degradê do briefing se perdeu.
        # Meio de cada curva (t=0.5 de uma quadrática: (p0+2c+p2)/4),
        # que é o ponto mais grosso do traço — na borda o antialiasing
        # atrapalharia a comparação.
        _r, _g, _b, perto = _pixel_no_desenho(self.ICONE, 289.5, 205)
        _r2, _g2, _b2, longe = _pixel_no_desenho(self.ICONE, 310, 205)
        self.assertGreater(perto, 200)
        self.assertGreater(longe, 0)
        self.assertLess(longe, perto)

    def test_todos_os_estados_tem_a_MESMA_silhueta(self):
        # Forma é identidade (é o vIsper), cor é estado — a decisão de
        # "cor de marca separada de cor de status" do CLAUDE.md, agora
        # aplicada à forma. Só o alpha pode ser comparado entre os
        # arquivos; o RGB muda de propósito.
        referencia = None
        for estado in gen.COLORS:
            with self.subTest(estado=estado):
                _w, _h, rows = _decode_png(ICON_DIR / f"{estado}.png")
                alphas = bytes(b for row in rows for b in row[3::4])
                if referencia is None:
                    referencia = alphas
                else:
                    self.assertEqual(alphas, referencia)


if __name__ == "__main__":
    unittest.main()

"""
Testa os ícones coloridos da barra de menu (status_icons/*.png,
gerados por design/generate_status_icons.py) — fecha o círculo entre
"a cor documentada em design/layouts_mockup.html" e "a cor que está
DE VERDADE nos bytes do PNG que main.py carrega".

Existe porque a reclamação real foi "as cores que você falou não
estão funcionando" — a v1 usava emoji como indicador de estado, e
emoji tem as cores do FONTE da Apple, não as da paleta semântica
documentada (🟠 não é terracota, por exemplo). Sem um teste ligando os
dois pontos, um PNG gerado com a cor errada (ou um mockup atualizado
sem regenerar os ícones) passaria batido.

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
                # Opaco no centro — é um círculo sólido, não um anel.
                self.assertEqual(a, 255)

    def test_bordas_sao_transparentes_fora_do_circulo(self):
        # Confirma que É um círculo (com antialiasing), não um
        # quadrado — os 4 cantos do canvas devem ficar fora do raio e
        # sair com alpha 0.
        for estado in gen.COLORS:
            with self.subTest(estado=estado):
                _w, _h, rows = _decode_png(ICON_DIR / f"{estado}.png")
                canto = rows[0][0:4]
                self.assertEqual(canto[3], 0, "canto do PNG devia ser transparente")


if __name__ == "__main__":
    unittest.main()

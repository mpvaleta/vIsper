#!/bin/bash
#
# build_mac_app.sh — gera vIsper.app (e um vIsper.dmg em volta dele) a
# partir do código Python, pra abrir com duplo clique em vez de
# `python3 main.py` num Terminal aberto.
#
# Uso:
#   ./build_mac_app.sh          # standalone: .app autocontido + .dmg
#   ./build_mac_app.sh --dev    # alias: build em segundos, pra testar
#
# Diferença entre os dois (detalhe completo no topo de setup.py):
# standalone leva o Python e todas as libs pra dentro do .app (grande,
# mas sobrevive a apagar a pasta); --dev faz o .app apontar pro venv
# daqui (rápido, mas quebra se a pasta sair do lugar).
#
# Só roda em macOS — precisa de sips/iconutil/hdiutil, que são
# ferramentas da Apple.

set -euo pipefail

cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"
VENV="$PROJECT_DIR/venv"
ALIAS_MODE=0

if [ "${1:-}" = "--dev" ]; then
    ALIAS_MODE=1
fi

# ---------------------------------------------------------------------
# 0. Confere que dá pra fazer isso aqui
# ---------------------------------------------------------------------
if [ "$(uname)" != "Darwin" ]; then
    echo "ERRO: isso só roda num Mac (precisa de sips/iconutil/hdiutil)."
    exit 1
fi

# ---------------------------------------------------------------------
# 1. venv — o MESMO usado pra rodar manualmente, de propósito
#
# Permissão de microfone/Acessibilidade no macOS é concedida por
# binário. Usar um venv separado só pro build faria o macOS tratar o
# resultado como outro app e pedir tudo de novo.
# ---------------------------------------------------------------------
if [ ! -d "$VENV" ]; then
    echo "==> Criando venv em $VENV"
    python3 -m venv "$VENV"
fi

echo "==> Instalando dependências (+ py2app)"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r requirements.txt
"$VENV/bin/pip" install --quiet py2app

# ---------------------------------------------------------------------
# 2. Ícone: PNG do mascote -> .icns (formato que o macOS exige)
#
# O .icns precisa de várias resoluções dentro dele. A arte de origem
# tem 400x400, então os tamanhos acima disso são upscale — fica um
# pouco macio, aceitável porque o mascote ainda é conceito (a Valeta
# não reagiu aos designs ainda, ver CLAUDE.md). Trocar depois é só
# substituir o PNG de origem e rodar de novo.
# ---------------------------------------------------------------------
ICON_SRC="design/mascot_concept_v1_preview.png"
ICONSET="build/vIsper.iconset"
ICNS="design/vIsper.icns"

echo "==> Gerando $ICNS a partir de $ICON_SRC"
rm -rf "$ICONSET"
mkdir -p "$ICONSET"
for size in 16 32 128 256 512; do
    sips -z $size $size "$ICON_SRC" \
        --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
    sips -z $((size * 2)) $((size * 2)) "$ICON_SRC" \
        --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$ICNS"

# ---------------------------------------------------------------------
# 3. O build em si
# ---------------------------------------------------------------------
echo "==> Limpando builds anteriores"
rm -rf build/bdist.* dist

if [ "$ALIAS_MODE" = "1" ]; then
    echo "==> Build ALIAS (rápido, amarrado a esta pasta)"
    "$VENV/bin/python" setup.py py2app -A
else
    echo "==> Build STANDALONE (demora — são centenas de MB de libs nativas)"
    "$VENV/bin/python" setup.py py2app
fi

# ---------------------------------------------------------------------
# 4. Assinatura ad-hoc
#
# Não é assinatura de desenvolvedor de verdade (isso custa US$99/ano e
# este projeto tem custo zero como princípio — ver CLAUDE.md). O
# ad-hoc só dá ao app uma identidade ESTÁVEL, o que importa porque o
# macOS amarra as permissões concedidas (mic/Acessibilidade) à
# assinatura: sem isso, toda recompilação pediria tudo de novo.
# ---------------------------------------------------------------------
echo "==> Assinando ad-hoc"
codesign --force --deep --sign - "dist/vIsper.app" 2>/dev/null || \
    echo "    (aviso: codesign falhou — o app funciona igual, só vai" \
         "pedir permissão de novo a cada rebuild)"

if [ "$ALIAS_MODE" = "1" ]; then
    echo
    echo "PRONTO (modo --dev): dist/vIsper.app"
    echo "Arraste pro Dock ou dê duplo clique. NÃO mova a pasta do vIsper."
    exit 0
fi

# ---------------------------------------------------------------------
# 5. DMG — só no modo standalone (um .dmg de build alias instalaria um
#    atalho quebrado)
# ---------------------------------------------------------------------
echo "==> Montando vIsper.dmg"
DMG_ROOT="build/dmg"
rm -rf "$DMG_ROOT" vIsper.dmg
mkdir -p "$DMG_ROOT"
cp -R "dist/vIsper.app" "$DMG_ROOT/"
ln -s /Applications "$DMG_ROOT/Applications"   # o arrastar-pra-cá clássico

hdiutil create \
    -volname "vIsper" \
    -srcfolder "$DMG_ROOT" \
    -ov -format UDZO \
    "vIsper.dmg" >/dev/null

echo
echo "PRONTO:"
echo "  dist/vIsper.app   — dá pra arrastar direto pra /Applications"
echo "  vIsper.dmg        — o instalador ($(du -h vIsper.dmg | cut -f1))"
echo
echo "Abra o .dmg, arraste o vIsper pra Applications, e abra ele."
echo "Na PRIMEIRA vez use botão direito -> Abrir (o app não é assinado"
echo "por um desenvolvedor pago, então o duplo clique é bloqueado)."

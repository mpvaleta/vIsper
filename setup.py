"""
setup.py — empacota o vIsper como um .app de verdade (py2app), pra
abrir com duplo clique no Finder em vez de `python3 main.py` num
Terminal aberto.

Não roda direto — use `./build_mac_app.sh`, que cuida do venv, do
ícone (.icns) e do .dmg em volta disso. Só num Mac.

Dois modos, os dois via build_mac_app.sh:
  - padrão (standalone): copia o Python e TODAS as libs pra dentro do
    .app. Fica grande (~300-500 MB por causa do ctranslate2/onnxruntime
    que vêm com o faster-whisper), mas é autocontido — sobrevive a
    apagar a pasta do projeto.
  - --dev (alias): o .app vira um atalho pro venv da pasta. Build em
    segundos e muito menos coisa pra dar errado, MAS quebra se a pasta
    do vIsper mudar de lugar ou o venv sumir. Bom pra testar rápido.

Por que LSUIElement = True: o vIsper é um app de barra de menu. Sem
isso ele também apareceria no Dock e no Cmd+Tab, que não é o que a
gente quer.

Por que as duas NS*UsageDescription: sem elas, o macOS moderno MATA o
app na hora que ele tenta abrir o microfone ou mandar um AppleScript,
em vez de mostrar o diálogo de permissão. Rodando por Terminal quem
pedia permissão era o Terminal; num .app é o próprio .app — por isso
elas só passam a ser obrigatórias aqui.
"""

import os
import sys

from setuptools import setup

APP = ["main.py"]


def _portaudio_dylib():
    """
    Caminho do libportaudio que vem dentro da roda do sounddevice.

    Precisa ir pro bundle à mão. O sounddevice procura essa lib por um
    caminho RELATIVO ao próprio sounddevice.py; dentro de um .app o
    módulo acaba num zip, o caminho relativo deixa de existir, e o
    import falha — o que, num app sem Terminal, aparece como um ícone
    que nunca surge e nenhuma explicação em lugar nenhum. Listar o
    pacote em PACKAGES resolve metade (tira do zip); o dylib em si
    ainda precisa ser copiado.

    Devolve None se não achar (ex.: sounddevice instalado contra um
    PortAudio do sistema, via Homebrew) — nesse caso não há o que
    copiar e o py2app resolve pelo caminho normal.
    """
    try:
        import sounddevice  # noqa: F401  (só pra descobrir onde ele está)
    except Exception:
        return None

    base = os.path.dirname(os.path.abspath(sounddevice.__file__))
    for pasta in (base, os.path.dirname(base)):
        candidato = os.path.join(pasta, "_sounddevice_data", "portaudio-binaries")
        if not os.path.isdir(candidato):
            continue
        for nome in os.listdir(candidato):
            if nome.endswith(".dylib"):
                return os.path.join(candidato, nome)
    return None

# Módulos locais do projeto. py2app segue os imports sozinho, mas
# listar explícito evita que algum caminho só alcançado em runtime
# (ex.: o Porcupine, que só é importado se as chaves existirem) fique
# de fora do bundle.
LOCAL_MODULES = [
    "actions",
    "audio_file_input",
    "audio_input",
    "command_router",
    "config",
    "dictation",
    "porcupine_session",
    "relay_listener",
    "text_utils",
    # config.py importa este na PRIMEIRA linha — sem ele no bundle, o
    # .app morre no import de config, antes de qualquer outra coisa.
    "user_settings",
    "wake_word_porcupine",
]

# Pacotes que precisam ir INTEIROS pro bundle. faster-whisper puxa
# libs nativas (ctranslate2, onnxruntime, av) que o py2app não
# consegue rastrear só pelos imports — se faltar aqui, o .app abre e
# morre no primeiro import. sounddevice entra inteiro também porque
# carrega o PortAudio de dentro de _sounddevice_data/.
PACKAGES = [
    "av",
    "certifi",
    "ctranslate2",
    "faster_whisper",
    "huggingface_hub",
    "numpy",
    "onnxruntime",
    "requests",
    "rumps",
    "sounddevice",
    "tokenizers",
]

FRAMEWORKS = [caminho for caminho in [_portaudio_dylib()] if caminho]

OPTIONS = {
    # NUNCA True: argv_emulation depende do Carbon, que não existe mais
    # em macOS 64-bit — trava o app na abertura. O vIsper não recebe
    # argumento de linha de comando de qualquer forma.
    "argv_emulation": False,
    "iconfile": "design/vIsper.icns",
    "packages": PACKAGES,
    "includes": LOCAL_MODULES,
    "frameworks": FRAMEWORKS,
    "plist": {
        "CFBundleName": "vIsper",
        "CFBundleDisplayName": "vIsper",
        "CFBundleIdentifier": "com.valeta.visper",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "LSMinimumSystemVersion": "11.0",
        # App de barra de menu: sem ícone no Dock, sem Cmd+Tab.
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        # Texto em inglês de propósito: aparece no diálogo de permissão
        # do macOS, então é UI de produto (ver CLAUDE.md).
        "NSMicrophoneUsageDescription": (
            "vIsper listens for your wake word and dictation so it can "
            "open the right AI chat and type what you said."
        ),
        "NSAppleEventsUsageDescription": (
            "vIsper uses automation to open your AI chat, paste the "
            "dictated text, and press Enter for you."
        ),
    },
}

setup(
    name="vIsper",
    app=APP,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)

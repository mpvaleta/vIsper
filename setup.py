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

from setuptools import setup

APP = ["main.py"]

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

OPTIONS = {
    # NUNCA True: argv_emulation depende do Carbon, que não existe mais
    # em macOS 64-bit — trava o app na abertura. O vIsper não recebe
    # argumento de linha de comando de qualquer forma.
    "argv_emulation": False,
    "iconfile": "design/vIsper.icns",
    "packages": PACKAGES,
    "includes": LOCAL_MODULES,
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

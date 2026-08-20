"""
doctor.py — confere a configuração antes de rodar o app de verdade,
pra pegar erro de config na hora em vez de descobrir só quando algo
falhar caladinho no meio do uso. Rodar com:

    python3 doctor.py

Não substitui rodar e testar o app de verdade — só pega o que dá pra
conferir sem mic, sem AccessKey, sem nada além do que já está no
disco/config.py.
"""

import importlib.util
import sys
from pathlib import Path

import config
from user_settings import settings_path


def _ok(msg):
    print(f"  OK   {msg}")


def _warn(msg):
    print(f"  AVISO {msg}")


def _fail(msg):
    print(f"  FALHA {msg}")


def check_python_version():
    print("Versão do Python:")
    versao = sys.version_info
    atual = f"{versao.major}.{versao.minor}.{versao.micro}"

    # A janela real é estreita e não é arbitrária:
    #   - abaixo de 3.9: o numpy 1.26.4 (requirements.txt) não tem roda.
    #   - acima de 3.12: idem — o numpy 1.26.4 não publica roda pra
    #     3.13+, então `pip install -r requirements.txt` cai num build
    #     de fonte e falha.
    #   - o Python 3.9 que já vem no macOS funciona pros testes, mas o
    #     py2app (o .app) precisa de um build com framework, que o do
    #     sistema não é.
    if versao < (3, 9):
        _fail(f"Python {atual} é antigo demais — instale o 3.11 (brew install python@3.11)")
        return 1
    if versao >= (3, 13):
        _fail(
            f"Python {atual}: o numpy 1.26.4 do requirements.txt não tem roda "
            "pra 3.13+, então a instalação falha. Use o 3.11 "
            "(brew install python@3.11 && python3.11 -m venv venv)"
        )
        return 1
    if versao < (3, 10):
        _warn(
            f"Python {atual} roda o app, mas empacotar o .app (py2app) "
            "precisa de 3.10+ com build de framework — o Python que já vem "
            "no macOS não serve pra isso"
        )
        return 0
    _ok(f"Python {atual}")
    return 0


def check_settings_source():
    """
    Mostra de ONDE cada valor veio.

    Sem isto, "meu tópico não funciona" e "o tópico nem estava sendo
    lido" são a mesma tela — e a segunda é o que acontece quando o
    settings.json tem um erro de digitação no nome de uma chave, ou está
    num caminho diferente do esperado.
    """
    print("\nConfiguração pessoal:")
    caminho = settings_path()
    if not caminho.exists():
        _warn(
            f"nenhum settings.json em {caminho} — usando só os padrões do "
            "config.py. Rode `python3 setup_visper.py` pra criar."
        )
        return 0

    if not config.OVERRIDDEN_KEYS:
        _fail(
            f"{caminho} existe mas NENHUM valor dele foi aplicado — provável "
            "erro de digitação num nome de chave, ou valor com o tipo errado "
            "(ver user_settings.VALIDATORS). Rode `python3 setup_visper.py` "
            "pra regravar."
        )
        return 1

    _ok(f"lido de {caminho}")
    _ok(f"sobrepondo: {', '.join(config.OVERRIDDEN_KEYS)}")

    modo = caminho.stat().st_mode & 0o777
    if modo & 0o077:
        _warn(
            f"{caminho} está legível por outros usuários da máquina "
            f"({oct(modo)}) e guarda o tópico do ntfy — rode "
            f"`chmod 600 {caminho}`"
        )
    return 0


def check_dependencies():
    print("Dependências:")
    problems = 0
    required = ["rumps", "sounddevice", "numpy", "faster_whisper", "requests"]
    for mod in required:
        if importlib.util.find_spec(mod) is None:
            _fail(f"'{mod}' não está instalado — rode: pip install -r requirements.txt")
            problems += 1
        else:
            _ok(mod)

    # pvporcupine só é obrigatório se ela configurou o Porcupine
    if config.PORCUPINE_ACCESS_KEY or config.PORCUPINE_KEYWORD_PATH:
        if importlib.util.find_spec("pvporcupine") is None:
            _fail("'pvporcupine' não instalado, mas PORCUPINE_* está configurado em config.py")
            problems += 1
        else:
            _ok("pvporcupine")
    return problems


def check_input_device():
    print("\nMicrofone de entrada:")
    problems = 0

    # Import atrasado de propósito, mesmo padrão do `import actions` em
    # check_ai_config(): se 'sounddevice'/PortAudio não estiver instalado
    # ainda, isso é responsabilidade de check_dependencies() reportar —
    # aqui só tentamos, sem derrubar o resto do doctor.py se faltar.
    try:
        import audio_input
    except Exception as exc:
        _warn(
            f"não consegui checar dispositivos agora ({exc}) — normal se "
            "'sounddevice' ou o PortAudio (brew install portaudio) ainda não "
            "estiverem instalados; não é um problema de config.py"
        )
        return problems

    try:
        devices = audio_input.list_input_devices()
    except Exception as exc:
        _warn(f"'sounddevice' importou mas não consegui listar dispositivos agora ({exc})")
        return problems

    if not devices:
        _warn("nenhum dispositivo de entrada encontrado pelo sistema agora — normal se nada estiver plugado/pareado ainda")
        return problems

    found = audio_input.guess_preferred_device()
    if found:
        index, name, is_bluetooth = found
        tag = " — Bluetooth, ver aviso de qualidade no README" if is_bluetooth else ""
        _ok(f"dispositivo preferido detectado: [{index}] {name}{tag}")
    else:
        names = ", ".join(f"'{name}'" for _index, name in devices)
        padrao = audio_input.default_input_device()
        if padrao:
            _ok(
                f"nenhum dispositivo preferido por perto, mas o vIsper vai "
                f"usar o padrão do sistema: '{padrao[1]}'"
            )
            _warn(
                f"pra um deles ganhar automaticamente, acrescente em "
                f"config.PREFERRED_INPUT_DEVICES. Disponíveis: {names}"
            )
        else:
            _warn(
                f"{len(devices)} dispositivo(s) listado(s) ({names}) mas nenhum "
                "utilizável como entrada agora"
            )
    return problems


def check_ntfy_topic():
    print("\nRelay do iPhone (ntfy):")
    problems = 0
    topic = config.NTFY_TOPIC
    if not topic:
        _warn("NTFY_TOPIC vazio — relay desligado, só o mic local funciona (tudo bem se for isso mesmo por enquanto)")
        return problems

    weak_examples = {"visper", "vIsper", "test", "teste", "topic", "topico", "mac", "valeta"}
    if topic.lower() in weak_examples or len(topic) < 20:
        _fail(
            f"NTFY_TOPIC ('{topic}') parece curto ou óbvio demais — "
            "o nome do tópico É a senha que impede qualquer pessoa de "
            "digitar no seu Mac. Rode `python3 setup_visper.py` pra "
            "sortear um de verdade"
        )
        problems += 1
    else:
        _ok(f"NTFY_TOPIC configurado, {len(topic)} caracteres — parece aleatório o bastante")

    if config.RELAY_BLOCKED_AIS:
        _ok(
            f"o iPhone NÃO pode abrir: {', '.join(config.RELAY_BLOCKED_AIS)} "
            "(segunda tranca, ver config.RELAY_BLOCKED_AIS)"
        )
    else:
        _warn(
            "RELAY_BLOCKED_AIS está vazio — quem souber o tópico consegue "
            "abrir o Terminal e digitar nele, o que é execução de comando"
        )
    return problems


def check_porcupine():
    print("\nWake word acústica (Porcupine):")
    key = config.PORCUPINE_ACCESS_KEY
    path = config.PORCUPINE_KEYWORD_PATH
    problems = 0

    if not key and not path:
        _warn("PORCUPINE_ACCESS_KEY e PORCUPINE_KEYWORD_PATH vazios — usando só o modo Whisper contínuo (tudo bem se ainda não configurou)")
        return problems

    if bool(key) != bool(path):
        _fail("só um dos dois (PORCUPINE_ACCESS_KEY / PORCUPINE_KEYWORD_PATH) está preenchido — precisa dos dois juntos")
        problems += 1
    else:
        _ok("PORCUPINE_ACCESS_KEY preenchido")
        if Path(path).exists():
            _ok(f"arquivo .ppn encontrado em {path}")
        else:
            _fail(f"PORCUPINE_KEYWORD_PATH aponta pra um arquivo que não existe: {path}")
            problems += 1
    return problems


def check_ai_config():
    print("\nConfiguração de IAs:")
    problems = 0
    if config.DEFAULT_AI not in config.AI_TRIGGERS:
        _fail(f"DEFAULT_AI ('{config.DEFAULT_AI}') não é nenhuma das chaves em AI_TRIGGERS")
        problems += 1
    else:
        _ok(f"DEFAULT_AI ('{config.DEFAULT_AI}') existe em AI_TRIGGERS")

    import actions
    for ai_name in config.AI_TRIGGERS:
        if ai_name not in actions.AI_ACTIONS:
            _fail(f"'{ai_name}' está em AI_TRIGGERS mas não tem ação correspondente em actions.AI_ACTIONS")
            problems += 1
    if problems == 0:
        _ok("toda chave de AI_TRIGGERS tem uma ação em actions.AI_ACTIONS")
    return problems


def main():
    total_problems = 0
    total_problems += check_python_version()
    total_problems += check_settings_source()
    total_problems += check_dependencies()
    total_problems += check_input_device()
    total_problems += check_ntfy_topic()
    total_problems += check_porcupine()
    total_problems += check_ai_config()

    print()
    if total_problems == 0:
        print("Tudo certo por aqui — o que sobra só dá pra testar rodando de verdade.")
    else:
        print(f"{total_problems} coisa(s) pra corrigir antes de rodar.")
    sys.exit(1 if total_problems else 0)


if __name__ == "__main__":
    main()

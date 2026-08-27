"""
user_settings.py — configuração PESSOAL, guardada FORA do repositório.

Por que isso existe (dois motivos, os dois concretos):

1. SEGURANÇA. O repositório do vIsper é PÚBLICO no GitHub. O
   `NTFY_TOPIC` é o único segredo que impede qualquer pessoa do mundo
   de disparar automação de verdade no Mac (abrir apps, colar texto,
   apertar Enter). Antes, o README mandava colar o tópico direto no
   `config.py` — que é versionado. Um `git push` distraído publicaria
   a chave da casa. O mesmo vale pra `PORCUPINE_ACCESS_KEY`, que é
   uma credencial de conta.

2. DISTRIBUIR PRA OUTRAS PESSOAS. Config pessoal dentro do código-fonte
   quer dizer que cada pessoa precisa editar arquivo `.py` e que
   atualizar o vIsper (git pull) dá conflito com o que ela mudou. Com o
   arquivo separado, o código atualiza sozinho e a configuração de cada
   um sobrevive.

Como funciona: `config.py` continua sendo a fonte dos PADRÕES (e a
documentação de cada opção). No fim dele, `apply_overrides()` sobrepõe
o que existir em

    ~/Library/Application Support/vIsper/settings.json

Quem lê `config.NTFY_TOPIC` (ou faz `from config import WAKE_WORD`)
recebe o valor final já sobreposto, sem saber que isso aconteceu — foi
de propósito, pra não precisar mexer em nenhum outro módulo.

Filosofia de erro, igual à do `device.json` em `audio_input.py`:
arquivo faltando, JSON quebrado, disco ilegível ou valor com o tipo
errado NUNCA derrubam o app. Cai no padrão do `config.py` e segue. É
conveniência, não deve impedir o vIsper de abrir — ainda mais porque,
num `.app` empacotado, não há Terminal pra mostrar o erro.
"""

import json
import os
from pathlib import Path

# Mesma pasta do device.json (audio_input.py) — um lugar só pro estado
# do vIsper, e um lugar só pra apagar se quiser começar do zero.
SETTINGS_DIR = Path.home() / "Library" / "Application Support" / "vIsper"
SETTINGS_PATH = SETTINGS_DIR / "settings.json"

# Variável de ambiente que sobrepõe o caminho — usada pelos testes (pra
# nunca tocar no arquivo de verdade da pessoa) e útil pra quem quiser
# manter a config em outro lugar.
ENV_OVERRIDE = "VISPER_SETTINGS_PATH"


def settings_path() -> Path:
    """Caminho efetivo do settings.json (respeita a env var)."""
    custom = os.environ.get(ENV_OVERRIDE)
    return Path(custom) if custom else SETTINGS_PATH


# ---------------------------------------------------------------------
# Validação
#
# Cada chave sobreponível diz que FORMA aceita. Um valor com tipo errado
# é descartado individualmente — o resto do arquivo continua valendo. O
# contrário (descartar o arquivo inteiro por causa de uma linha errada)
# seria mais frustrante: a pessoa erra o tipo de um campo e perde a
# configuração toda sem entender por quê.
# ---------------------------------------------------------------------

def _is_str(value):
    return isinstance(value, str)


def _is_bool(value):
    return isinstance(value, bool)


def _is_positive_int(value):
    # bool é subclasse de int em Python: sem excluir explicitamente,
    # `true` num campo numérico passaria como 1.
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_lang_code_list(value):
    """TRANSCRIPTION_LANGUAGES: lista de códigos curtos ("pt", "en").
    Lista VAZIA é válida e significa "sem restrição". Não valida contra
    a lista completa de códigos do Whisper (mudaria a cada versão do
    modelo), só a FORMA."""
    return isinstance(value, list) and all(
        isinstance(v, str) and 2 <= len(v) <= 8 for v in value
    )


def _is_probability(value):
    """LANGUAGE_CONFIDENCE_THRESHOLD: fração entre 0 e 1."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and 0.0 <= value <= 1.0
    )


def _is_match_ratio(value):
    """FUZZY_MATCH_THRESHOLD: fração entre 0.5 e 1.0 (1.0 = só exato).
    Abaixo de 0.5 qualquer palavra casa com qualquer outra — isso não é
    uma configuração, é o app abrindo IA por conta própria."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and 0.5 <= value <= 1.0
    )


def _is_str_list(value):
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _is_triggers_map(value):
    """{"claude": ["claude", "cláudio"], ...}"""
    return (
        isinstance(value, dict)
        and value  # dicionário vazio deixaria o app sem nenhuma IA
        and all(isinstance(k, str) and _is_str_list(v) for k, v in value.items())
    )


def _is_device_groups(value):
    """[{"keywords": [...], "bluetooth": bool}, ...]"""
    if not isinstance(value, list):
        return False
    for group in value:
        if not isinstance(group, dict):
            return False
        if not _is_str_list(group.get("keywords", None) or []):
            return False
        if not group.get("keywords"):
            return False
        if not isinstance(group.get("bluetooth", False), bool):
            return False
    return True


# chave -> validador. Só o que está aqui pode ser sobreposto: um
# settings.json não deve conseguir injetar nome novo em config.
VALIDATORS = {
    "WAKE_WORD": _is_str,
    "DEFAULT_AI": _is_str,
    "NTFY_TOPIC": _is_str,
    "PORCUPINE_ACCESS_KEY": _is_str,
    "PORCUPINE_KEYWORD_PATH": _is_str,
    "CLOSE_TRIGGERS": _is_str_list,
    "CANCEL_TRIGGERS": _is_str_list,
    "TRANSCRIPTION_LANGUAGES": _is_lang_code_list,
    "LANGUAGE_CONFIDENCE_THRESHOLD": _is_probability,
    "FUZZY_MATCH_THRESHOLD": _is_match_ratio,
    "RELAY_BLOCKED_AIS": _is_str_list,
    "RELAY_MAX_MESSAGE_CHARS": _is_positive_int,
    "AI_TRIGGERS": _is_triggers_map,
    "PREFERRED_INPUT_DEVICES": _is_device_groups,
    "DICTATION_SOUNDS_ENABLED": _is_bool,
    "DICTATION_OPEN_SOUND": _is_str,
    "DICTATION_SEND_SOUND": _is_str,
    "DICTATION_CANCEL_SOUND": _is_str,
}


def load_settings() -> dict:
    """
    Lê o settings.json e devolve só os pares válidos. Devolve {} pra
    qualquer problema (não existe, JSON quebrado, sem permissão, não é
    um objeto no topo).
    """
    try:
        raw = settings_path().read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError):
        return {}

    if not isinstance(data, dict):
        return {}

    clean = {}
    for key, value in data.items():
        validator = VALIDATORS.get(key)
        if validator and validator(value):
            clean[key] = value
    return clean


def save_settings(values: dict) -> bool:
    """
    Grava (mesclando com o que já existe) as chaves válidas de `values`.
    Devolve True se conseguiu. Passar None num valor REMOVE a chave,
    fazendo ela voltar pro padrão do config.py.

    Usado pelo assistente de primeira configuração (setup_visper.py) e
    pelo menu do app.
    """
    merged = load_settings()
    for key, value in values.items():
        if key not in VALIDATORS:
            continue
        if value is None:
            merged.pop(key, None)
        elif VALIDATORS[key](value):
            merged[key] = value

    try:
        path = settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        # Só a dona lê/escreve: o arquivo guarda o tópico do ntfy, que é
        # o que protege o Mac de automação remota (ver docstring do topo).
        os.chmod(path, 0o600)
        return True
    except OSError:
        return False


def apply_overrides(namespace: dict) -> list:
    """
    Sobrepõe, DENTRO de `namespace` (na prática `globals()` do
    config.py), tudo que o settings.json definir de válido.

    Devolve a lista de chaves sobrepostas — o doctor.py usa isso pra
    mostrar de onde cada valor veio, que é a diferença entre "meu
    tópico não funciona" e "ah, ele nem estava sendo lido".

    Só sobrepõe chave que JÁ EXISTE no namespace: um settings.json não
    deve conseguir criar configuração que o código não conhece.
    """
    applied = []
    for key, value in load_settings().items():
        if key in namespace:
            namespace[key] = value
            applied.append(key)

    # Rede de segurança: se o settings.json trocou AI_TRIGGERS e deixou
    # DEFAULT_AI apontando pra uma IA que não existe mais, o app abriria
    # e nunca conseguiria abrir a IA padrão. Volta pra primeira
    # disponível em vez de quebrar.
    triggers = namespace.get("AI_TRIGGERS")
    default_ai = namespace.get("DEFAULT_AI")
    if isinstance(triggers, dict) and triggers and default_ai not in triggers:
        namespace["DEFAULT_AI"] = next(iter(triggers))

    return sorted(applied)

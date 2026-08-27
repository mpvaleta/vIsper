#!/usr/bin/env python3
"""
check_no_secrets.py — guarda de segurança pro repositório PÚBLICO.

O `NTFY_TOPIC` é, na prática, a senha que impede qualquer pessoa do
mundo de disparar automação de verdade no Mac (abrir apps, colar texto,
apertar Enter). O `PORCUPINE_ACCESS_KEY` é credencial de conta. Os dois
precisam morar em ~/Library/Application Support/vIsper/settings.json,
fora do repositório — ver user_settings.py.

Este script confere que ninguém preencheu esses campos no `config.py`
por engano (o jeito antigo, ainda descrito em README de versões
anteriores). Roda no CI a cada push, e dá pra rodar à mão:

    python3 check_no_secrets.py

Lê o config.py como TEXTO (ast), não importando ele — assim o valor
real da pessoa, que vem do settings.json, não é confundido com o que
está escrito no arquivo versionado.
"""

import ast
import subprocess
import sys
from pathlib import Path

# Campos que nunca podem ter valor dentro do config.py versionado.
CAMPOS_SENSIVEIS = {
    "NTFY_TOPIC": (
        "é a senha que protege seu Mac de automação remota — qualquer "
        "pessoa que ler o repositório poderia usar"
    ),
    "PORCUPINE_ACCESS_KEY": "é a credencial da sua conta na Picovoice",
}

# Arquivos que nunca deveriam estar rastreados pelo git.
ARQUIVOS_PROIBIDOS = ["settings.json", "device.json"]


def valores_literais(caminho: Path) -> dict:
    """Nome -> valor, só pras atribuições literais no topo do arquivo."""
    encontrados = {}
    try:
        tree = ast.parse(caminho.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return encontrados

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Constant):
            continue
        for alvo in node.targets:
            if isinstance(alvo, ast.Name):
                encontrados[alvo.id] = node.value.value
    return encontrados


def arquivos_rastreados() -> list:
    try:
        saida = subprocess.run(
            ["git", "ls-files"], capture_output=True, text=True, check=True
        )
        return saida.stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        return []


def main() -> int:
    problemas = []

    valores = valores_literais(Path("config.py"))
    for campo, porque in CAMPOS_SENSIVEIS.items():
        valor = valores.get(campo)
        if isinstance(valor, str) and valor.strip():
            problemas.append(
                f"config.py define {campo} = {valor!r}\n"
                f"    Isso {porque}.\n"
                f"    O config.py é versionado num repositório PÚBLICO.\n"
                f"    Correção: apague o valor de lá e rode "
                f"`python3 setup_visper.py`."
            )

    rastreados = arquivos_rastreados()
    for proibido in ARQUIVOS_PROIBIDOS:
        for caminho in rastreados:
            if Path(caminho).name == proibido:
                problemas.append(
                    f"{caminho} está rastreado pelo git — esse arquivo tem "
                    f"configuração pessoal e não deveria ir pro repositório.\n"
                    f"    Correção: git rm --cached {caminho}"
                )

    if problemas:
        print("PROBLEMAS DE SEGURANÇA:\n")
        for i, problema in enumerate(problemas, 1):
            print(f"  {i}. {problema}\n")
        return 1

    print("OK — nenhum segredo no repositório.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

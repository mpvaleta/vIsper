#!/usr/bin/env python3
"""
setup_visper.py — assistente de primeira configuração.

Existe pra você nunca precisar abrir um arquivo `.py` pra configurar o
vIsper. Ele pergunta o mínimo, sorteia o que dá pra sortear, e grava
tudo em

    ~/Library/Application Support/vIsper/settings.json

que fica FORA do repositório (o repo do vIsper é público — ver o
cabeçalho de user_settings.py pro porquê isso importa).

Rode assim, e pode só ir apertando Enter pra aceitar tudo:

    python3 setup_visper.py

Não precisa de nenhuma dependência instalada (nem venv ativado): usa
só a biblioteca padrão do Python, de propósito, porque a primeira coisa
que a pessoa faz é justamente antes de instalar qualquer coisa.

Rodar de novo depois é seguro: os valores atuais viram o padrão de cada
pergunta, então Enter em tudo não muda nada.
"""

import secrets
import subprocess
import sys
from urllib.parse import quote

import config
from user_settings import save_settings, settings_path

# Onde o app de iPhone (PWA) mora — publicado pelo GitHub Pages a
# partir da pasta docs/ deste mesmo repositório.
PWA_URL = "https://mpvaleta.github.io/vIsper/"


# ---------------------------------------------------------------------
# Perguntas
# ---------------------------------------------------------------------

def ask(pergunta: str, atual: str) -> str:
    """Pergunta mostrando o valor atual como padrão. Enter mantém."""
    mostrado = atual if atual else "(vazio)"
    try:
        resposta = input(f"{pergunta}\n  [{mostrado}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelado — nada foi alterado.")
        sys.exit(1)
    return resposta if resposta else atual


def ask_sim_nao(pergunta: str, padrao_sim: bool = True) -> bool:
    dica = "S/n" if padrao_sim else "s/N"
    try:
        resposta = input(f"{pergunta} [{dica}]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelado — nada foi alterado.")
        sys.exit(1)
    if not resposta:
        return padrao_sim
    return resposta.startswith("s") or resposta.startswith("y")


def novo_topico() -> str:
    """Tópico do ntfy: longo e aleatório de propósito.

    O nome do tópico É a senha (ntfy.sh não tem outra) — quem souber
    ele consegue mandar comando pro Mac. 24 bytes de entropia é o
    bastante pra ninguém adivinhar nem varrer por força bruta.
    """
    return "visper-" + secrets.token_urlsafe(24)


def copiar(texto: str) -> bool:
    """Coloca no clipboard do Mac. Falha silenciosa (é conveniência)."""
    try:
        subprocess.run(["pbcopy"], input=texto.encode("utf-8"), check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


# ---------------------------------------------------------------------

def main():
    print()
    print("═" * 62)
    print("  vIsper — configuração")
    print("═" * 62)
    print()
    print(f"  Vai ser gravado em: {settings_path()}")
    print("  (fora do repositório, então não vai parar no GitHub)")
    print()

    novos = {}

    # -- wake word ----------------------------------------------------
    print("─" * 62)
    wake = ask(
        "1) Qual palavra ativa o vIsper?\n"
        "   Dica: o reconhecimento é por transcrição, então palavra REAL\n"
        "   e distinta funciona melhor que inventada. 'Vésper', 'Íris' e\n"
        "   'Sussurro' acertam mais que 'vIsper'.",
        config.WAKE_WORD,
    )
    if wake != config.WAKE_WORD:
        novos["WAKE_WORD"] = wake

    # -- IA padrão ----------------------------------------------------
    print("─" * 62)
    while True:
        default_ai = ask(
            "2) Qual IA abre quando você fala só a palavra de ativação?\n"
            f"   Opções: {', '.join(config.AI_TRIGGERS)}",
            config.DEFAULT_AI,
        )
        if default_ai in config.AI_TRIGGERS:
            break
        print(f"   '{default_ai}' não existe. Escolha uma da lista acima.")
    if default_ai != config.DEFAULT_AI:
        novos["DEFAULT_AI"] = default_ai

    # -- ntfy ---------------------------------------------------------
    print("─" * 62)
    print("3) Usar o iPhone pra disparar comando no Mac de qualquer lugar?")
    print("   (é o que faz funcionar longe de casa, tipo no treino)")
    print()

    topico = config.NTFY_TOPIC
    if topico:
        print(f"   Já existe um tópico configurado: {topico}")
        if ask_sim_nao("   Sortear um NOVO (invalida o atual)?", padrao_sim=False):
            topico = novo_topico()
            novos["NTFY_TOPIC"] = topico
    elif ask_sim_nao("   Ativar?", padrao_sim=True):
        topico = novo_topico()
        novos["NTFY_TOPIC"] = topico
        print(f"\n   Tópico sorteado: {topico}")
        print("   Isto é uma SENHA. Não poste em lugar nenhum.")

    # -- Porcupine (opcional) -----------------------------------------
    print("─" * 62)
    print("4) Wake word acústica (Porcupine)? — opcional, pule se não sabe")
    print("   Reconhece o SOM da palavra em vez da transcrição. Precisa de")
    print("   conta grátis em console.picovoice.ai. Sem isso o vIsper usa")
    print("   o modo Whisper contínuo, que já funciona.")
    if ask_sim_nao("   Configurar agora?", padrao_sim=False):
        chave = ask("   AccessKey da Picovoice:", config.PORCUPINE_ACCESS_KEY)
        caminho = ask("   Caminho do arquivo .ppn:", config.PORCUPINE_KEYWORD_PATH)
        if chave:
            novos["PORCUPINE_ACCESS_KEY"] = chave
        if caminho:
            novos["PORCUPINE_KEYWORD_PATH"] = caminho

    # -- grava --------------------------------------------------------
    print("═" * 62)
    if not novos:
        print("  Nada mudou — a configuração continua como estava.")
    elif save_settings(novos):
        print(f"  Salvo: {', '.join(sorted(novos))}")
        print(f"  Em: {settings_path()}")
    else:
        print("  ERRO: não consegui gravar o arquivo de configuração.")
        print(f"  Confira as permissões de {settings_path().parent}")
        return 1

    # -- próximos passos ----------------------------------------------
    print()
    print("═" * 62)
    print("  PRÓXIMOS PASSOS")
    print("═" * 62)
    print()
    print("  No Mac:")
    print("    python3 doctor.py     # confere se está tudo certo")
    print("    python3 main.py       # abre o ícone na barra de menu")
    print()

    if topico:
        # Wake word vai junto pro app do iPhone montar a mesma frase que
        # este Mac espera — se ela trocar a palavra e o iPhone não
        # souber, o Mac ignora tudo que vier de lá, calado.
        link = f"{PWA_URL}#t={topico}&w={quote(wake)}"
        print("  No iPhone — abra este link no Safari do iPhone e depois")
        print("  Compartilhar → Adicionar à Tela de Início:")
        print()
        print(f"    {link}")
        print()
        print("  (o tópico vai depois do #, que o navegador NÃO manda pro")
        print("   servidor — ele fica só no seu aparelho)")
        print()
        if copiar(link):
            print("  ✓ link copiado — cole no iPhone (AirDrop, Notas, WhatsApp")
            print("    pra você mesmo, ou a Área de Transferência Universal)")
            print()
        print("  Pra testar o relay sem o iPhone, aqui mesmo no Mac:")
        # `wake`, não `config.WAKE_WORD`: o config foi lido na importação,
        # ANTES de salvar — usar ele aqui imprimiria a palavra antiga e o
        # comando de teste não funcionaria.
        print(f'    curl -d "{wake} {default_ai} teste over" \\')
        print(f"         https://ntfy.sh/{topico}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())

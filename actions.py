"""
actions.py — as ações concretas que o vIsper executa quando reconhece
um comando.

Cada função aqui deve ser rápida e não-bloqueante: abre um app ou URL e
retorna na hora, sem esperar o app terminar de carregar.

Todo subprocess.run() aqui usa check=True de propósito: sem isso, uma
falha (ex.: permissão de Acessibilidade ainda não concedida — ver
handle_done()) fazia a ação simplesmente NÃO FAZER NADA, sem erro
nenhum — quem chamou não tinha como saber que o "cola e manda" falhou.
Com check=True, a falha vira CalledProcessError; quem chama por voz
(main.py, via DictationSession) já está preparado pra isso —
_listen_loop_safe() captura e avisa por notificação, em vez de morrer
calado ou fingir que funcionou.
"""

import subprocess


def _open_url(url: str):
    subprocess.run(["open", url], check=True)


def _open_app(app_name: str):
    subprocess.run(["open", "-a", app_name], check=True)


def open_claude():
    _open_url("https://claude.ai/new")


def open_claude_code():
    """
    Abre o Terminal e inicia uma sessão nova do Claude Code.
    Ajuste o diretório de trabalho abaixo (hoje é o home) se quiser
    outro padrão.
    """
    script = '''
    tell application "Terminal"
        activate
        do script "cd ~ && claude"
    end tell
    '''
    subprocess.run(["osascript", "-e", script], check=True)


def open_perplexity():
    _open_url("https://www.perplexity.ai/")


def open_chatgpt():
    _open_url("https://chat.openai.com/")


def open_gemini():
    _open_url("https://gemini.google.com/app")


def paste_text(text: str):
    """
    Coloca o texto no clipboard e simula Cmd+V na janela em foco.
    Mais rápido e confiável que simular tecla por tecla — não erra
    acento nem emoji, e funciona em qualquer campo de texto que
    aceite colar (o que cobre o chat de qualquer uma das IAs aqui).
    """
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
    script = 'tell application "System Events" to keystroke "v" using command down'
    subprocess.run(["osascript", "-e", script], check=True)


def play_sound(name: str):
    """
    Toca um som já embutido no macOS (/System/Library/Sounds/*.aiff) —
    feedback sonoro rápido de mudança de estado (ver config.py,
    DICTATION_OPEN_SOUND/DICTATION_SEND_SOUND).

    Ao contrário do resto deste arquivo, é non-blocking DE PROPÓSITO
    (Popen, não run) e engole falha em vez de propagar: isso é só
    estética (earcon), não deve segurar o loop de ditado esperando o
    som terminar, nem contar como "a ação falhou" se o som não tocar
    por algum motivo (ex.: nome inválido) — bem diferente de
    paste_text/handle_done, onde a falha É a ação real não acontecendo.
    """
    if not name:
        return
    try:
        subprocess.Popen(
            ["afplay", f"/System/Library/Sounds/{name}.aiff"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


def handle_done():
    """
    Sinal de 'manda ver' — simula apertar Enter na janela em foco,
    pra IA começar a trabalhar em cima do que já estiver no campo de
    chat (digitado, colado, ou ditado por outro app tipo o próprio
    Wispr Flow ou o ditado nativo do macOS).

    Precisa de permissão de Acessibilidade pro Terminal/Python em
    Ajustes do Sistema → Privacidade e Segurança → Acessibilidade —
    sem isso o System Events não consegue simular a tecla, e agora
    (check=True) isso vira um erro visível em vez de um Enter que
    simplesmente nunca chega.
    """
    script = 'tell application "System Events" to keystroke return'
    subprocess.run(["osascript", "-e", script], check=True)


# Chaves aqui têm que bater com as chaves de AI_TRIGGERS em config.py
AI_ACTIONS = {
    "claude": open_claude,
    "claude_code": open_claude_code,
    "chatgpt": open_chatgpt,
    "perplexity": open_perplexity,
    "gemini": open_gemini,
}

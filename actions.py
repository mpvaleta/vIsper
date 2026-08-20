"""
actions.py — as ações concretas que o vIsper executa quando reconhece
um comando.

Cada função aqui deve ser rápida e não-bloqueante: abre um app ou URL e
retorna na hora, sem esperar o app terminar de carregar.

Tudo passa por _run(), que usa check=True de propósito: sem isso, uma
falha (ex.: permissão de Acessibilidade ainda não concedida — ver
handle_done()) fazia a ação simplesmente NÃO FAZER NADA, sem erro
nenhum — quem chamou não tinha como saber que o "cola e manda" falhou.
Com check=True a falha vira exceção; quem chama por voz (main.py, via
DictationSession) já está preparado pra isso — _listen_loop_safe()
captura e avisa, em vez de morrer calado ou fingir que funcionou.

E _run() ainda separa um caso do resto: recusa de PERMISSÃO vira
AutomationDenied, não CalledProcessError genérica. Isso importa porque
é a falha mais provável da primeira execução e a única cuja correção é
um caminho fixo de Ajustes do Sistema — misturada com as outras, ela
virava "erro no áudio" e mandava investigar o microfone à toa.

A exceção da exceção é play_sound(), que engole falha de propósito —
earcon não pode travar o ditado nem parecer que a ação real falhou.
"""

import subprocess


class AutomationDenied(Exception):
    """
    O macOS recusou simular teclado / controlar outro app.

    Existe pra separar ESSA falha das outras. Ela é, de longe, a mais
    provável na primeira execução — o macOS só pede as permissões de
    Acessibilidade e de Automação quando o app tenta usá-las pela
    primeira vez, e até alguém marcar a caixinha em Ajustes toda colagem
    falha. Sem essa distinção, main.py reportava tudo como "erro no
    áudio", mandando investigar o microfone quando o microfone estava
    perfeito e o que faltava era um clique em Ajustes do Sistema.
    """


# Trechos que o osascript devolve quando a recusa é de PERMISSÃO, não
# um erro de script. Os códigos são estáveis; o texto em volta muda com
# o idioma do sistema, por isso a checagem é pelos números também.
_NEGADO = (
    "not allowed assistive access",
    "not authorized to send apple events",
    "-1719",   # errAEEventNotPermitted / sem acesso assistivo
    "-25211",  # System Events sem acesso assistivo
    "-1743",   # sem permissão de Automação pro app alvo
)


def _run(cmd, **kwargs):
    """
    subprocess.run com check=True, traduzindo recusa de permissão em
    AutomationDenied.

    Captura o stderr (antes ele ia direto pro terminal e se perdia) pra
    conseguir olhar a mensagem — é o que permite distinguir "o macOS não
    deixou" de "o script estava errado".
    """
    try:
        return subprocess.run(cmd, check=True, capture_output=True, **kwargs)
    except subprocess.CalledProcessError as exc:
        erro = (exc.stderr or b"")
        if isinstance(erro, bytes):
            erro = erro.decode("utf-8", "replace")
        if any(marca in erro.lower() for marca in _NEGADO):
            raise AutomationDenied(erro.strip() or "permission denied") from exc
        # Reanexa o stderr na mensagem: com capture_output, o texto do
        # osascript não aparece mais sozinho no terminal, e sem isso a
        # notificação de erro mostraria só "exit status 1".
        raise subprocess.CalledProcessError(
            exc.returncode, exc.cmd, exc.output, exc.stderr
        ) from None


def _open_url(url: str):
    _run(["open", url])


def _open_app(app_name: str):
    _run(["open", "-a", app_name])


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
    _run(["osascript", "-e", script])


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
    _run(["pbcopy"], input=text.encode("utf-8"))
    script = 'tell application "System Events" to keystroke "v" using command down'
    _run(["osascript", "-e", script])


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
    _run(["osascript", "-e", script])


# Chaves aqui têm que bater com as chaves de AI_TRIGGERS em config.py
AI_ACTIONS = {
    "claude": open_claude,
    "claude_code": open_claude_code,
    "chatgpt": open_chatgpt,
    "perplexity": open_perplexity,
    "gemini": open_gemini,
}

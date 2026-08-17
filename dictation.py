"""
dictation.py — a máquina de estados entre 'ocioso' (esperando um
comando tipo "vIsper, abre o claude") e 'ditando' (acumulando o que
você fala depois disso, até ouvir o sinal de fechamento).

Isso é o que faz o vIsper ser a interface completa: não só abre a IA,
também captura sua fala, cola ela no chat, e manda — sem você
precisar digitar nada nem usar outro app de ditado.

Fluxo:
  "vIsper, abre o claude"  -> abre o Claude, entra em modo ditado
  "posso te ajudar com X"  -> vai pro buffer (isso é o conteúdo)
  "mais uma frase aqui"    -> também vai pro buffer
  "câmbio" / "over"        -> cola o buffer inteiro no chat, aperta
  (ou "vIsper" de novo)       Enter, volta pro modo ocioso

Isso tudo pode caber numa respiração só também — "vIsper claude qual é
a previsão do tempo over" abre, dita e manda de uma vez, num único
trecho transcrito. Abertura e fechamento são checados no mesmo texto,
não só em chamadas separadas.

O sinal de fechamento é a wake word de novo OU qualquer uma das
palavras em config.CLOSE_TRIGGERS (hoje: "câmbio"/"over" — emprestado
do vocabulário de rádio, ver config.py pro raciocínio completo).
Casa como PALAVRA INTEIRA (text_utils.py), não substring — por isso
"over" não confunde com "however"/"moreover"/"cover".

Risco conhecido: se algum dos gatilhos de fechamento aparecer por
acidente no meio do que você está ditando, a ditância corta e manda
cedo demais. "câmbio"/"over" foram escolhidos justamente por serem
raros o bastante em fala natural pra isso ser improvável — mas ainda
é uma palavra real, não impossível de aparecer. Trocar pro Porcupine
(ver README) reduz isso pra detecção acústica de verdade, embora hoje
o Porcupine só reconheça a wake word em si, não os CLOSE_TRIGGERS
novos (cada palavra que ele reconhece precisa do próprio treino em
console.picovoice.ai — ver nota em wake_word_porcupine.py).
"""

from config import WAKE_WORD, CLOSE_TRIGGERS
from text_utils import contains_word, split_before_any

# Tudo que fecha um ditado: a própria wake word de novo, mais os
# CLOSE_TRIGGERS. Uma lista só, pra checagem e recorte não poderem
# divergir (a checagem dizer "fecha" e o recorte não achar onde
# cortar, ou vice-versa).
CLOSE_WORDS = [WAKE_WORD] + list(CLOSE_TRIGGERS)


def _has_close_trigger(text: str) -> bool:
    return any(contains_word(text, word) for word in CLOSE_WORDS)


class DictationSession:
    def __init__(self, router, paste_action, send_action, on_open=None, on_send=None):
        """
        router: CommandRouter — decide se/qual IA abrir
        paste_action: função(texto) -> None — cola o texto no chat
        send_action: função() -> None — aperta Enter pra mandar
        on_open: função() -> None opcional, chamada quando o ditado
                 ABRE (uma IA acabou de ser lançada). Só feedback
                 (ex.: som) — não afeta a máquina de estados.
        on_send: função() -> None opcional, chamada quando o ditado
                 FECHA COM CONTEÚDO de verdade (colou + mandou Enter).
                 NÃO é chamada no caso "cancelado" (fechou sem nada
                 ditado) — silêncio já é feedback razoável pra "nada
                 aconteceu".
        """
        self.router = router
        self.paste_action = paste_action
        self.send_action = send_action
        self.on_open = on_open
        self.on_send = on_send
        self.dictating = False
        self.buffer = []

    def handle(self, transcript: str):
        """
        Processa um pedaço de texto transcrito. Retorna uma string
        curta descrevendo o que aconteceu (pra notificação/log), ou
        None se não houve nenhuma ação.
        """
        text = transcript.strip()
        if not text:
            return None

        if not self.dictating:
            matched = self.router.route(text)
            if not matched:
                return None

            ai_name, leftover = matched
            self.dictating = True
            self.buffer = []
            if self.on_open:
                self.on_open()
            opened = f"abriu {ai_name} — ouvindo ditado"
            if not leftover:
                return opened

            # `leftover` é o conteúdo real que veio no MESMO trecho que
            # o comando de abrir — ex.: "vIsper claude qual é a
            # previsão do tempo" tudo numa respiração só. Sem isso, só
            # o nome da IA seria usado e o resto descartado.
            #
            # E esse mesmo trecho pode trazer o gatilho de FECHAMENTO
            # junto ("vIsper claude qual é a previsão do tempo over" —
            # pedido inteiro numa respiração só, que é justamente o
            # jeito mais natural de usar isso). Antes, o "over" ia pro
            # buffer como se fosse conteúdo: o ditado ficava aberto pra
            # sempre esperando um fechamento que já tinha sido dito, e
            # quando enfim fechasse a palavra "over" ia colada no texto
            # mandado pra IA. As duas pontas (abertura e fechamento) já
            # tinham sido corrigidas separadamente; faltava o caso em
            # que as duas caem no MESMO trecho.
            if _has_close_trigger(leftover):
                return f"{opened}; {self._close(leftover)}"

            self.buffer = [leftover]
            return opened

        if _has_close_trigger(text):
            return self._close(text)

        self.buffer.append(text)
        return "ditando…"

    def _close(self, text: str):
        """
        Fecha o ditado a partir do trecho que contém o gatilho: junta o
        buffer acumulado com o que veio ANTES do gatilho nesse mesmo
        trecho, cola e manda. Volta pro estado ocioso mesmo quando não
        havia nada pra mandar.
        """
        # Resgata conteúdo real que veio no MESMO trecho transcrito que
        # o gatilho de fechamento, antes de fechar — comum terminar a
        # frase e já emendar "over"/"câmbio" sem pausa, os dois caindo
        # no mesmo chunk do Whisper. Sem isso, esse trecho inteiro
        # seria perdido (só o buffer de chamadas ANTERIORES entraria na
        # mensagem final).
        prefix = split_before_any(text, CLOSE_WORDS)
        if prefix:
            self.buffer.append(prefix)

        full_text = " ".join(self.buffer).strip()
        self.dictating = False
        self.buffer = []
        if not full_text:
            return "cancelado (nada foi ditado)"

        self.paste_action(full_text)
        self.send_action()
        if self.on_send:
            self.on_send()
        return "mandou: " + full_text[:60]

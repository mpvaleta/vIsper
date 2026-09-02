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
  "vIsper, cancela"        -> joga o buffer fora SEM colar nada e
                              volta pro modo ocioso

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

import threading

from config import (
    WAKE_WORD,
    CLOSE_TRIGGERS,
    CANCEL_TRIGGERS,
    AI_TRIGGERS,
    FUZZY_MATCH_THRESHOLD,
)
from text_utils import (
    contains_word,
    find_trigger_span,
    split_after_word,
    split_before_any,
    starts_with_word,
    strip_trailing_word,
    trim_for_content,
)

# Tudo que fecha um ditado: a própria wake word de novo, mais os
# CLOSE_TRIGGERS. Uma lista só, pra checagem e recorte não poderem
# divergir (a checagem dizer "fecha" e o recorte não achar onde
# cortar, ou vice-versa).
CLOSE_WORDS = [WAKE_WORD] + list(CLOSE_TRIGGERS)


def _has_close_trigger(text: str) -> bool:
    return any(contains_word(text, word) for word in CLOSE_WORDS)


def _is_cancel(text: str) -> bool:
    """"vIsper, cancela" — desistir do ditado em vez de mandar.

    Exige a palavra de cancelar IMEDIATAMENTE depois da wake word, não
    só em algum lugar do mesmo trecho. A diferença não é preciosismo,
    é o que separa comando de conversa: "cancela"/"cancel" são
    palavras normais do dia a dia, então "preciso cancelar a reserva,
    vIsper" (fechar um ditado que POR ACASO falava em cancelar) teria
    virado "joga tudo fora" — o oposto exato do pedido, e
    irreversível. Com a adjacência, essa frase fecha e manda
    normalmente, e só "vIsper, cancela" cancela.

    Ver config.CANCEL_TRIGGERS pro raciocínio da escolha das palavras.
    """
    resto = split_after_word(text, WAKE_WORD)
    if not resto:
        return False
    return any(starts_with_word(resto, word) for word in CANCEL_TRIGGERS)


def _strip_leading_trigger(text: str, trigger: str):
    """Tira `trigger` do COMEÇO de `text`, se ele estiver lá.

    Devolve (texto_sem_o_gatilho, achou). Casa com a MESMA tolerância a
    erro de transcrição da abertura (find_trigger_span com
    FUZZY_MATCH_THRESHOLD): a wake word que vem do telefone pode estar
    escrita diferente da do Mac — "Vesper" contra "vIsper" — e exigir
    igualdade exata fazia o protocolo inteiro ("Vesper claude ") ser
    colado no chat como se fosse fala.

    Só o COMEÇO, nunca no meio: procurar em qualquer lugar apagava
    conteúdo de verdade. Ex.: "me lembra de perguntar pro gemini sobre
    isso" virava "sobre isso", porque "gemini" é apelido de uma IA —
    palavras somem no meio da frase, e a frase mutilada já foi colada e
    o Enter já foi apertado quando alguém percebe.
    """
    span = find_trigger_span(text, trigger, FUZZY_MATCH_THRESHOLD)
    if span is None:
        return text, False
    if text[: span[0]].strip(" \t\n.,;:!?-—…\"'"):
        return text, False  # apareceu, mas no meio: é conteúdo
    return trim_for_content(text[span[1]:]), True


def _relay_content(text: str, router, ai_id=None) -> str:
    """O que, numa mensagem do relay, é CONTEÚDO de verdade.

    O app de iPhone monta "<wake> <ia> <texto> over" numa string só, e
    o Atalho/Siri montam "<wake> <texto> over" — ou seja, o começo de
    toda mensagem é protocolo, não fala. Quando a mensagem ABRE o
    ditado, command_router já devolve esse resto separado
    (`leftover`). Quando ela chega com um ditado JÁ ABERTO pelo mic, o
    texto inteiro ia pro buffer cru: a wake word e o nome da IA eram
    colados no chat literalmente, no meio da frase que estava sendo
    ditada.

    Só o PREFIXO é removido, nunca um gatilho encontrado no meio — ver
    _strip_leading_trigger() pro conteúdo real que a versão anterior
    apagava. Com `ai_id` (o app já disse qual IA é, fora do texto — ver
    relay_listener.py) só os apelidos DAQUELA IA são considerados, o
    que é o que desarma a colisão "claude" × "claude code" sem tocar no
    roteador.
    """
    resto, _achou = _strip_leading_trigger(text, WAKE_WORD)

    if ai_id:
        apelidos = AI_TRIGGERS.get(ai_id, ())
    else:
        apelidos = [t for ts in AI_TRIGGERS.values() for t in ts]

    # Do mais COMPRIDO pro mais curto, senão um apelido que seja
    # prefixo de outro ("claude" dentro de "claude code") cortaria cedo
    # demais — a mesma razão do desempate em command_router._decide().
    for trigger in sorted(apelidos, key=len, reverse=True):
        sem_apelido, achou = _strip_leading_trigger(resto, trigger)
        if achou:
            return sem_apelido
    return resto


class DictationSession:
    def __init__(
        self,
        router,
        paste_action,
        send_action,
        on_open=None,
        on_send=None,
        on_cancel=None,
    ):
        """
        router: CommandRouter — decide se/qual IA abrir
        paste_action: função(texto) -> None — cola o texto no chat
        send_action: função() -> None — aperta Enter pra mandar
        on_open: função() -> None opcional, chamada quando o ditado
                 ABRE (uma IA acabou de ser lançada). Só feedback
                 (ex.: som) — não afeta a máquina de estados.
        on_send: função() -> None opcional, chamada quando o ditado
                 FECHA COM CONTEÚDO de verdade (colou + mandou Enter).
                 NÃO é chamada quando o fechamento não tinha nada pra
                 mandar — silêncio já é feedback razoável pra "nada
                 aconteceu".
        on_cancel: função() -> None opcional, chamada quando você
                 CANCELA de propósito ("vIsper, cancela"). Aqui o
                 feedback é obrigatório do ponto de vista de uso, não
                 opcional como nos outros: sem sinal nenhum não dá pra
                 saber se o texto foi mandado ou jogado fora — que é
                 exatamente a dúvida que o cancelamento existe pra
                 tirar. main.py toca um som DIFERENTE do de mandar.
        """
        self.router = router
        self.paste_action = paste_action
        self.send_action = send_action
        self.on_open = on_open
        self.on_send = on_send
        self.on_cancel = on_cancel
        self.dictating = False
        self.buffer = []
        # Guarda dictating/buffer contra o mic e o relay do iPhone
        # rodando em THREADS diferentes sobre a MESMA sessão de
        # propósito (main.py inicia as duas como threads daemon
        # separadas — ver CLAUDE.md, "compartilhar a instância evita
        # dois estados desencontrados"). Sem isto havia uma corrida de
        # verdade: "if not self.dictating" podia ser lida por AMBAS as
        # threads antes de qualquer uma escrever True, porque no meio
        # tem uma chamada BLOQUEANTE de verdade (router.route() ->
        # subprocess.run() abrindo o app) entre a leitura e a escrita —
        # janela larga o bastante pra um comando quase simultâneo pelo
        # mic e pelo iPhone abrir DUAS IAs e perder o conteúdo de uma
        # das duas. RLock (não Lock): os métodos privados de fechamento
        # são chamados de DENTRO de handle()/handle_complete(), que já
        # seguram o lock.
        self._lock = threading.RLock()

    def handle(self, transcript: str):
        """
        Processa um pedaço de texto transcrito AO VIVO (mic local, um
        chunk por vez — pode ser só parte de uma frase). Retorna uma
        string curta descrevendo o que aconteceu (pra notificação/log),
        ou None se não houve nenhuma ação.

        Fecha ao ouvir a wake word de novo ou qualquer CLOSE_TRIGGERS
        dentro do texto — necessário aqui porque um chunk de mic nunca
        vem com um sinal explícito de "isto é tudo". Canais que já
        entregam a mensagem INTEIRA de uma vez (o relay do iPhone) usam
        handle_complete() em vez desta, que não tem esse risco — ver lá
        o porquê.
        """
        with self._lock:
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
                opened = f"opened {ai_name} — listening for dictation"
                if not leftover:
                    return opened

                # `leftover` é o conteúdo real que veio no MESMO trecho
                # que o comando de abrir — ex.: "vIsper claude qual é a
                # previsão do tempo" tudo numa respiração só. Sem isso,
                # só o nome da IA seria usado e o resto descartado.
                #
                # E esse mesmo trecho pode trazer o gatilho de
                # FECHAMENTO junto ("vIsper claude qual é a previsão do
                # tempo over" — pedido inteiro numa respiração só, que é
                # justamente o jeito mais natural de usar isso). Antes,
                # o "over" ia pro buffer como se fosse conteúdo: o
                # ditado ficava aberto pra sempre esperando um
                # fechamento que já tinha sido dito, e quando enfim
                # fechasse a palavra "over" ia colada no texto mandado
                # pra IA. As duas pontas (abertura e fechamento) já
                # tinham sido corrigidas separadamente; faltava o caso
                # em que as duas caem no MESMO trecho.
                # Cancelar vem ANTES de fechar aqui pelo mesmo motivo de
                # baixo: "vIsper cancela" contém a wake word, que também
                # é gatilho de fechamento — sem esta ordem, o
                # fechamento ganharia e mandaria justamente o que você
                # pediu pra jogar fora.
                if _is_cancel(leftover):
                    return f"{opened}; {self._cancel()}"
                if _has_close_trigger(leftover):
                    return f"{opened}; {self._close(leftover)}"

                self.buffer = [leftover]
                return opened

            # ORDEM IMPORTA: a wake word é gatilho de fechamento, e
            # "vIsper cancela" contém a wake word. Se o fechamento fosse
            # checado primeiro, pedir pra cancelar MANDARIA o ditado —
            # o oposto exato do que foi pedido, e irreversível.
            if _is_cancel(text):
                return self._cancel()

            if _has_close_trigger(text):
                return self._close(text)

            self.buffer.append(text)
            return "dictating…"

    def handle_complete(self, transcript: str, ai_id=None, blocked_ais=None):
        """
        Processa um comando que já chega INTEIRO e pronto (hoje: o
        relay do iPhone — ver relay_listener.py). Abre a IA do mesmo
        jeito que handle() (mesmo router, mesma tolerância a erro de
        transcrição/digitação), mas o conteúdo depois do nome da IA só
        tem o marcador de fechamento removido se ele estiver GRUDADO NO
        FIM (strip_trailing_word) — nunca procurado no meio do texto.

        Por quê: handle() precisa procurar um gatilho de fechamento EM
        QUALQUER LUGAR do texto porque um chunk de mic pode conter
        abertura e fechamento juntos, sem pausa, e o gatilho marca
        "parei de falar AQUI". O iPhone não tem esse problema — cada
        mensagem que ele manda (docs/index.html, buildMessage()) já É
        a mensagem completa, com um "over" GRUDADO NO FIM por
        construção, sempre, em TODA mensagem, só pra sinalizar "isto é
        tudo" pro parser, não como algo que a pessoa quis dizer. Bug
        real que isso corrigiu: usando o mesmo "procura em qualquer
        lugar" do mic, qualquer conteúdo dita/digitada que já
        contivesse a palavra "over" (ex.: "let's talk this over") ou
        "câmbio" (ex.: "qual é o câmbio do dólar hoje") batia como
        fechamento ANTES do fim — split_before_any() cortava ali, e o
        texto TRUNCADO já tinha sido colado E o Enter já tinha sido
        apertado antes de qualquer um perceber. Se o próprio conteúdo
        começasse com "over"/"câmbio", a mensagem inteira era
        descartada e nada era mandado — os dois casos com o telefone
        mostrando "Sent to your Mac" de qualquer forma, porque o POST
        pro ntfy tinha sucesso mesmo quando o Mac não mandou nada ou
        mandou pela metade. strip_trailing_word() olha só o FIM, então
        um "over"/"câmbio" de verdade no meio da frase sobrevive, e só
        o marcador que o app grudou é removido.

        `ai_id` é a IA JÁ RESOLVIDA, quando o canal souber dela por
        fora do texto — hoje o app de iPhone, onde a pessoa TOCA num
        botão (ver relay_listener.py e CommandRouter.open()). Com ele o
        roteador de texto livre nem é consultado pra escolher o alvo, e
        o conteúdo não precisa mais começar com o nome de uma IA. Sem
        ele (Atalho/Siri, ou uma versão antiga do app), o caminho é o
        de sempre.

        Se uma sessão de mic já estiver aberta (self.dictating), o
        texto entra no buffer e fecha na hora — sem isso, uma mensagem
        do iPhone chegando no meio de um ditado por voz ficaria
        pendurada esperando um fechamento que essa mensagem nunca vai
        mandar (o iPhone não repete a chamada).
        """
        with self._lock:
            text = transcript.strip()
            if not text:
                return None

            if not self.dictating:
                if ai_id:
                    # A IA já vem RESOLVIDA (a pessoa tocou num botão);
                    # nada de roteador de texto livre — ver
                    # CommandRouter.open() pro bug real que isso
                    # corrige.
                    alvo = ai_id
                    leftover = _relay_content(text, self.router, ai_id)
                else:
                    # split_complete(), não route(): mensagem inteira e
                    # deliberada sem nome de IA abre a DEFAULT_AI, igual
                    # a "vIsper" sozinha no mic — ver
                    # CommandRouter.split_complete() pro porquê de o mic
                    # NÃO poder fazer isso.
                    matched = self.router.split_complete(text)
                    if not matched:
                        return None
                    alvo, leftover = matched

                # A trava de alvos proibidos mora DENTRO do lock, junto
                # da decisão que ela protege. Fora dele havia uma
                # janela real: o relay checava `dictating` primeiro e
                # PULAVA a checagem quando um ditado estava aberto —
                # mas entre a checagem e a ação o ditado do mic podia
                # fechar, e aí a mensagem abria justamente o alvo
                # proibido. Um gate só, no lugar certo.
                if blocked_ais and alvo in blocked_ais:
                    return f"ignored: '{alvo}' cannot be opened from the phone"

                ai_name = self.router.open(alvo)
                if ai_name is None:
                    return None
                self.dictating = True
                self.buffer = []
                if self.on_open:
                    self.on_open()
                opened = f"opened {ai_name} — listening for dictation"
                if not leftover:
                    return opened
                return f"{opened}; {self._close_verbatim(leftover)}"

            # Ditado JÁ ABERTO (pelo mic): esta mensagem é conteúdo, e
            # o começo dela é protocolo — sem tirar isso, "vIsper
            # claude" ia colado no chat no meio da frase.
            return self._close_verbatim(_relay_content(text, self.router, ai_id))

    def _cancel(self):
        """Joga o ditado fora sem colar nada. Nenhuma ação de verdade
        acontece — nada é colado, nenhum Enter é apertado."""
        perdido = len(" ".join(self.buffer).strip())
        self.dictating = False
        self.buffer = []
        if self.on_cancel:
            self.on_cancel()
        if not perdido:
            return "cancelled — nothing had been dictated"
        return f"cancelled — {perdido} character(s) discarded, nothing was sent"

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
        return self._finalize()

    def _close_verbatim(self, text: str):
        """Como _close(), mas só remove um marcador de fechamento se
        ele estiver GRUDADO NO FIM de `text` (strip_trailing_word) —
        nunca procurado no meio (ver handle_complete() pro porquê)."""
        self.buffer.append(strip_trailing_word(text, CLOSE_WORDS))
        return self._finalize()

    def _finalize(self):
        """Junta o buffer, cola, manda Enter, e volta pro estado
        ocioso. Compartilhado por _close() e _close_verbatim() — as
        duas só diferem em COMO preparam o buffer antes de chamar
        isto."""
        full_text = " ".join(self.buffer).strip()
        self.dictating = False
        self.buffer = []
        if not full_text:
            return "nothing to send — the dictation was empty"

        self.paste_action(full_text)
        self.send_action()
        if self.on_send:
            self.on_send()
        # O "…" importa: esta string vai pro "Recent activity", que é a
        # ferramenta de diagnóstico. Cortada em 60 sem marca nenhuma,
        # ela é indistinguível de uma mensagem que FOI mandada pela
        # metade — que é justamente o bug que já aconteceu de verdade
        # aqui (ver handle_complete()). O que foi colado é sempre o
        # texto INTEIRO; só a linha do log é que é curta.
        if len(full_text) > 60:
            return "sent: " + full_text[:60] + "…"
        return "sent: " + full_text

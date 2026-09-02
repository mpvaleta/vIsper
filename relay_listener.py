"""
relay_listener.py — ouve comandos vindos do app de iPhone via ntfy
(https://ntfy.sh), pra funcionar de qualquer lugar, não só na mesma
Wi-Fi do Mac (ex.: usar do treino, da rua).

Como funciona: o iPhone publica o texto do comando (mesmo formato que
o Whisper produziria, tipo "vIsper claude confirma a reunião") num
tópico do ntfy. Esse listener fica inscrito nesse tópico e, pra cada
mensagem que chegar, passa ela pro MESMO DictationSession que já
processa o áudio local — é o mesmo pipeline testado, só muda de onde
o texto vem.

IMPORTANTE (segurança): tópicos do ntfy.sh não têm senha por padrão —
quem souber o nome do tópico manda comando pro seu Mac, e isso aciona
automação de verdade (abrir apps, colar texto, simular Enter). O nome
do tópico É a senha; gere um longo e aleatório com `setup_visper.py`,
que guarda ele fora do repositório. Nunca algo óbvio tipo "visper" ou
o seu nome.

Segunda tranca, pro caso da primeira falhar: config.RELAY_BLOCKED_AIS
barra alvos que este canal não pode abrir mesmo com o tópico certo
(hoje: claude_code, que abre o Terminal e digita nele — vazar o tópico
viraria execução de comando, não só "digitar num chat"). E
config.RELAY_MAX_MESSAGE_CHARS corta mensagem gigante antes dela ser
colada inteira no chat.

NUNCA TESTADO DE VERDADE ainda — escrito com base na documentação
pública do ntfy (endpoint /json de streaming), mas o sandbox onde
isso foi escrito não tem acesso de rede ao ntfy.sh pra validar a
conexão de ponta a ponta. O que ESTÁ testado (ver test_relay_listener.py)
é a lógica de parsing e a integração com DictationSession, com a rede
simulada. Primeira coisa a validar de verdade quando estiver no Mac
com Claude Code: rodar isso contra o ntfy.sh real.
"""

import collections
import json
import time
import urllib.parse

import requests

import config


class RelayListener:
    # Primeira linha opcional de uma mensagem, com a IA JÁ RESOLVIDA
    # pelo app que mandou (ver _split_ai_header()).
    AI_HEADER = "#visper-ai="

    def __init__(
        self,
        session,
        topic: str,
        server: str = "https://ntfy.sh",
        blocked_ais=None,
        max_chars=None,
        on_message=None,
        backlog_max_seconds=None,
    ):
        """
        session: a mesma DictationSession usada pelo áudio local —
                 compartilhar a instância evita dois estados
                 "tô ditando ou não" desencontrados entre mic e ntfy.
        topic: nome do tópico ntfy (ver aviso de segurança acima).
        blocked_ais: IAs que este canal NÃO pode abrir (ver
                 config.RELAY_BLOCKED_AIS pro raciocínio — resumindo,
                 abrir o Terminal remotamente é execução de comando,
                 não "digitar num chat").
        max_chars: tamanho máximo de uma mensagem aceita.
        on_message: função opcional(str) -> None, chamada com o texto
                 BRUTO de toda mensagem recebida, ANTES de qualquer
                 trava ou tentativa de casar gatilho. Existe pro mesmo
                 motivo de main._set_heard() no mic: sem isso, uma wake
                 word desatualizada no telefone (trocada no Mac pelo
                 menu "Wake word…" sem atualizar o link do iPhone) faz
                 o roteador não bater com NADA — handle_complete()
                 devolve None, on_result nunca é chamado — e não sobra
                 rastro nenhum em "Recent activity", justo a ferramenta
                 feita pra diagnosticar esse tipo de falha silenciosa.
        backlog_max_seconds: janela de recuperação ao reconectar (ver
                 config.RELAY_BACKLOG_MAX_SECONDS). 0 desliga.
        """
        self.session = session
        self.topic = topic
        self.server = server.rstrip("/")
        self.running = False
        self.blocked_ais = set(
            config.RELAY_BLOCKED_AIS if blocked_ais is None else blocked_ais
        )
        self.max_chars = (
            config.RELAY_MAX_MESSAGE_CHARS if max_chars is None else max_chars
        )
        self.on_message = on_message
        self.backlog_max_seconds = (
            config.RELAY_BACKLOG_MAX_SECONDS
            if backlog_max_seconds is None
            else backlog_max_seconds
        )
        # Última mensagem ENTREGUE de verdade. É a âncora do `since=`
        # na reconexão (ver _subscribe_url()); None enquanto nenhuma
        # chegou, que é justamente quando NÃO se deve pedir histórico.
        self._last_message_id = None
        # IDs já processados, pra uma mensagem re-entregue pelo
        # `since=` não ser executada duas vezes. Curto de propósito: só
        # precisa cobrir o que uma única reconexão pode repetir.
        self._seen_ids = collections.deque(maxlen=64)

    def _split_ai_header(self, text: str):
        """Separa o cabeçalho "#visper-ai=<id>" do resto da mensagem.

        Devolve (ai_id, resto). `ai_id` é None quando não há cabeçalho,
        quando ele nomeia uma IA que não existe, ou quando o valor é
        lixo — nesses casos o texto volta INTEIRO e o caminho de sempre
        (adivinhar por texto livre) continua valendo.

        Por que um cabeçalho: no app de iPhone a pessoa TOCA no chip da
        IA, então o alvo é uma certeza. Mandar essa certeza embutida na
        prosa ("vIsper claude <texto> over") a transformava de volta em
        palpite — e conteúdo começando com "code"/"código" (ou
        parecido, o casamento é fuzzy) fazia o roteador ler "claude
        code", que RELAY_BLOCKED_AIS barra, sumindo com a mensagem
        inteira. Ver CommandRouter.open().

        Fica na PRIMEIRA LINHA, e o corpo continua sendo "<wake>
        <texto> over" completo de propósito: um Mac numa versão antiga
        ignora a linha do cabeçalho (ela vem ANTES da wake word, então
        o roteador nem olha pra ela) e continua funcionando pelo
        caminho velho. Assim atualizar só o telefone, ou só o Mac, não
        quebra nada.
        """
        if not text.startswith(self.AI_HEADER):
            return None, text
        cabecalho, _, resto = text.partition("\n")
        candidato = cabecalho[len(self.AI_HEADER):].strip()
        if candidato not in config.AI_TRIGGERS:
            # Nome inventado (ou versão futura do app): joga fora só o
            # cabeçalho e segue com o resto pelo caminho de texto livre.
            #
            # O cabeçalho é SEMPRE descartado, mesmo quando o resto fica
            # vazio. Antes havia um "ou o texto inteiro" aqui como rede
            # de segurança, e ele produzia um bug de verdade: uma
            # mensagem que fosse só "#visper-ai=xyz", sem quebra de
            # linha, voltava inteira — e como o casamento da wake word é
            # fuzzy, "visper" casava DENTRO do próprio cabeçalho. Com um
            # ditado do mic já aberto, isso virava "ai=xyz" colado no
            # chat e o Enter apertado. Voltar vazio é o certo: mensagem
            # sem conteúdo não faz nada, que é exatamente o desejado.
            return None, resto.strip()
        return candidato, resto.strip()

    def _handle_message(self, text: str):
        """
        Aplica as travas deste canal e entrega pro DictationSession.

        Devolve o mesmo que session.handle_complete() devolveria, ou
        uma string explicando a recusa. Recusa RETORNA texto em vez de
        ficar calada de propósito: uma mensagem sumindo sem explicação
        é indistinguível de "o relay não está funcionando".
        """
        if self.on_message:
            self.on_message(text)

        if len(text) > self.max_chars:
            return (
                f"ignored: message too large "
                f"({len(text)} characters, limit {self.max_chars})"
            )

        ai_id, corpo = self._split_ai_header(text)

        # A trava de RELAY_BLOCKED_AIS vai JUNTO da chamada, e é
        # aplicada lá dentro, sob o mesmo lock que decide e abre.
        #
        # Antes ela era um `if` aqui em cima, e tinha uma janela real:
        # a checagem era pulada quando um ditado já estava aberto
        # (`self.session.dictating`), mas entre ler isso e a mensagem
        # ser processada o ditado do mic podia FECHAR — e aí ela abria
        # justamente o alvo proibido. Também evita duas lógicas
        # paralelas decidindo qual é o alvo, que é como um filtro
        # separado acaba divergindo do roteador e liberando o que
        # deveria barrar.
        #
        # handle_complete(), não handle(): cada mensagem do relay já
        # chega INTEIRA (ver a docstring de handle_complete() em
        # dictation.py pro bug real que essa distinção corrige — texto
        # contendo "over"/"câmbio" sendo truncado ou descartado só por
        # causa do sufixo automático que o app de iPhone gruda em toda
        # mensagem).
        return self.session.handle_complete(
            corpo, ai_id=ai_id, blocked_ais=self.blocked_ais
        )

    def listen_forever(self, on_result=None):
        """
        Conecta no stream de eventos do tópico e processa cada
        mensagem que chegar. Reconecta sozinho se a conexão cair
        (rede instável, Mac saiu de suspensão, etc.) em vez de matar
        a thread pro resto da sessão do app.

        on_result: função opcional(str) -> None, chamada com o que
                   DictationSession.handle() retornar — pluga numa
                   notificação, igual ao loop de áudio local em
                   main.py.
        """
        self.running = True
        backoff_seconds = 5
        max_backoff_seconds = 60
        offline_desde = None

        while self.running:
            try:
                url = self._subscribe_url(offline_desde)
                with requests.get(url, stream=True, timeout=(10, 90)) as resp:
                    resp.raise_for_status()
                    backoff_seconds = 5  # reconectou de verdade, reseta o backoff
                    offline_desde = None
                    for line in resp.iter_lines():
                        if not self.running:
                            break
                        if not line:
                            continue  # linha de keepalive do ntfy, ignora
                        try:
                            event = json.loads(line)
                        except ValueError:
                            # Uma linha malformada (glitch de rede,
                            # proxy que injetou algo) é ruído de UMA
                            # mensagem — não é motivo pra derrubar uma
                            # conexão que está funcionando e esperar o
                            # backoff inteiro. Pula a linha e segue
                            # ouvindo.
                            continue
                        if event.get("event") != "message":
                            continue  # ignora "open"/keepalive, só processa mensagem
                        text = event.get("message", "")
                        if not text:
                            continue
                        # Uma mensagem repetida pelo `since=` da
                        # reconexão não pode abrir app/colar/mandar de
                        # novo — o ntfy pode reentregar a própria
                        # âncora, e reexecutar é irreversível.
                        msg_id = event.get("id")
                        if msg_id is not None:
                            if msg_id in self._seen_ids:
                                continue
                            self._seen_ids.append(msg_id)
                            self._last_message_id = msg_id
                        result = self._handle_message(text)
                        if result and on_result:
                            on_result(result)
            except requests.RequestException:
                # rede caiu ou o Mac saiu de suspensão — cai no mesmo
                # backoff do fim do loop, sem derrubar a thread.
                pass

            # Espera ANTES de reconectar, tenha a conexão morrido com
            # erro ou terminado limpa. O caso "terminou limpa" (ntfy
            # reiniciou, proxy fechou o stream por ociosidade) não
            # levanta exceção nenhuma: antes ele caía direto no próximo
            # `while`, reabrindo a conexão na hora, sem pausa — se o
            # servidor estivesse aceitando e fechando na sequência,
            # isso virava um laço de requisições HTTPS sem freio, à
            # toda velocidade, contra o ntfy.sh.
            #
            # Backoff exponencial (5s, 10s, 20s... até 60s) em vez de
            # fixo: recupera rápido de uma falha rápida, mas não fica
            # martelando o servidor numa queda longa. Reseta assim que
            # uma conexão dá certo de novo (acima).
            if not self.running:
                break
            # Marca o INÍCIO da queda uma vez só: o que interessa pro
            # `since=` é há quanto tempo estamos fora no total, não há
            # quanto tempo foi a última tentativa.
            if offline_desde is None:
                offline_desde = time.monotonic()
            time.sleep(backoff_seconds)
            backoff_seconds = min(backoff_seconds * 2, max_backoff_seconds)

    def _subscribe_url(self, offline_desde):
        """A URL do stream, com `since=` quando houver o que recuperar.

        O ntfy entrega, por padrão, só o que chega DEPOIS da conexão —
        então tudo que o iPhone publicou durante uma queda (ou durante
        o backoff, que chega a 60s) sumia sem deixar rastro, com o
        telefone mostrando "Sent to your Mac" do mesmo jeito. Pedir
        `since=<id da última vista>` reentrega essa janela.

        Três guardas, e nenhuma é opcional:
          - PRIMEIRA conexão (sem `offline_desde`) nunca pede
            histórico: abrir o app não pode executar o que foi dito
            antes dele existir.
          - sem `_last_message_id` também não pede: sem âncora, o
            `since` teria que ser uma duração, e errar pra mais
            reexecuta comando velho.
          - queda mais longa que `backlog_max_seconds` é considerada
            perdida de propósito (ver config.RELAY_BACKLOG_MAX_SECONDS):
            recuperar um comando de horas atrás é surpresa, não
            recuperação.
        """
        base = f"{self.server}/{self.topic}/json"
        if offline_desde is None or self._last_message_id is None:
            return base
        if self.backlog_max_seconds <= 0:
            return base
        if time.monotonic() - offline_desde > self.backlog_max_seconds:
            return base
        # O id vem do JSON do servidor, então nunca entra cru na URL:
        # um `&` ou `#` ali dentro viraria outro parâmetro (ou cortaria
        # a query) numa requisição que este app faz sozinho, em loop.
        return f"{base}?since={urllib.parse.quote(str(self._last_message_id), safe='')}"

    def stop(self):
        self.running = False

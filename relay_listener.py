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

import json
import time

import requests

import config


class RelayListener:
    def __init__(
        self,
        session,
        topic: str,
        server: str = "https://ntfy.sh",
        blocked_ais=None,
        max_chars=None,
        on_message=None,
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
                f"ignorado: mensagem grande demais "
                f"({len(text)} caracteres, limite {self.max_chars})"
            )

        # Só checa quando o texto ABRIRIA uma IA. Com o ditado já
        # aberto, o texto é conteúdo — não passa pelo roteador, então
        # não há alvo pra bloquear.
        if not self.session.dictating and self.blocked_ais:
            alvo = self.session.router.preview(text)
            if alvo in self.blocked_ais:
                return f"ignorado: '{alvo}' não pode ser aberto pelo iPhone"

        # handle_complete(), não handle(): cada mensagem do relay já
        # chega INTEIRA (ver a docstring de handle_complete() em
        # dictation.py pro bug real que essa distinção corrige — texto
        # contendo "over"/"câmbio" sendo truncado ou descartado só por
        # causa do sufixo automático que o app de iPhone gruda em toda
        # mensagem).
        return self.session.handle_complete(text)

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
        url = f"{self.server}/{self.topic}/json"
        backoff_seconds = 5
        max_backoff_seconds = 60

        while self.running:
            try:
                with requests.get(url, stream=True, timeout=(10, 90)) as resp:
                    resp.raise_for_status()
                    backoff_seconds = 5  # reconectou de verdade, reseta o backoff
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
            time.sleep(backoff_seconds)
            backoff_seconds = min(backoff_seconds * 2, max_backoff_seconds)

    def stop(self):
        self.running = False

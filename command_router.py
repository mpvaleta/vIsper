"""
command_router.py — decide se um texto transcrito deve ABRIR uma IA.

Isso cobre só o "abrir": wake word sozinha abre a IA padrão
(config.DEFAULT_AI), wake word + nome de uma IA (config.AI_TRIGGERS)
abre aquela IA. Qualquer outra coisa dita depois da wake word, que
não seja nome de IA, é ignorada aqui — não faz mais sentido tratar
como comando "manda ver" neste ponto, porque isso só existe DEPOIS
que uma IA já está aberta (ver dictation.py).
"""

from config import WAKE_WORD, DEFAULT_AI, AI_TRIGGERS, FUZZY_MATCH_THRESHOLD
from text_utils import find_trigger_span, trim_for_decision, trim_for_content


class CommandRouter:
    def __init__(self, ai_actions: dict):
        """ai_actions: dict {nome_da_ia: função}, vem de actions.AI_ACTIONS"""
        self.ai_actions = ai_actions

    def route(self, transcript: str):
        """
        Processa um texto transcrito, ABRINDO a IA escolhida. Retorna
        None se a wake word não apareceu ou não bateu com nada
        reconhecível; senão retorna (nome_da_ia, leftover) — `leftover`
        é o que sobrou depois do nome da IA (ou "" se foi só a wake word
        sozinha, abrindo DEFAULT_AI), com capitalização/acento/pontuação
        ORIGINAIS preservados (text_utils.text_after_word()), pra não
        perder conteúdo dito na MESMA respiração que o comando de abrir —
        ex.: "vIsper claude qual é a previsão do tempo" tudo de uma vez.
        Quem chama (dictation.py) decide o que fazer com esse resto.
        """
        decision = self._decide(transcript)
        if decision is None:
            return None
        ai_name, leftover = decision
        self.ai_actions[ai_name]()
        return ai_name, leftover

    def open(self, ai_name: str):
        """
        ABRE uma IA já resolvida, sem adivinhar nada por texto.

        Existe pro relay do iPhone (ver relay_listener.py): lá a pessoa
        TOCOU num botão, então a IA já é uma certeza — não faz sentido
        re-descobrir por texto livre o que o toque já sabia. Fazer isso
        era um bug real: o app mandava "vIsper claude <conteúdo> over"
        numa string só, e conteúdo que começasse com "code"/"código"
        (ou qualquer coisa parecida o bastante — o casamento é fuzzy,
        então "coding is hard" também batia) fazia o roteador preferir
        corretamente o gatilho de DUAS palavras "claude code" ao de uma
        só "claude". Como claude_code está em config.RELAY_BLOCKED_AIS
        por segurança, a mensagem inteira era recusada e sumia — com o
        telefone mostrando "Sent to your Mac" do mesmo jeito, porque o
        POST pro ntfy tinha dado 200.

        A regra de desempate do _decide() NÃO é o problema e não pode
        ser mexida: ela existe pro caso de VOZ equivalente ("vIsper
        claude code também abre um terminal" tem que abrir o Claude
        Code). O problema era jogar fora uma certeza e pedir pro
        roteador de voz adivinhar de novo.

        Retorna o nome da IA aberta, ou None se `ai_name` não for uma
        IA conhecida (nome inventado chegando pelo relay não pode
        virar KeyError e derrubar a thread de escuta).
        """
        if ai_name not in self.ai_actions:
            return None
        self.ai_actions[ai_name]()
        return ai_name

    def split(self, transcript: str):
        """
        O que route() DECIDIRIA, sem abrir nada: (nome_da_ia, leftover)
        ou None.

        Mesma decisão de route()/preview(), exposta inteira porque
        dictation.handle_complete() precisa das DUAS metades quando uma
        mensagem do iPhone chega no meio de um ditado já aberto: ali o
        texto é CONTEÚDO, então a wake word e o nome da IA que vêm
        grudados nele (o app monta "<wake> <ia> <texto> over" numa
        string só) têm que ser removidos antes de ir pro buffer — senão
        são colados no chat literalmente, como se a pessoa tivesse
        ditado "vIsper claude" no meio da frase.
        """
        return self._decide(transcript)

    def split_complete(self, transcript: str):
        """
        Como split(), mas pra mensagens que chegam INTEIRAS e
        deliberadas (o relay do iPhone): wake word + conteúdo sem
        nenhum nome de IA reconhecível abre a DEFAULT_AI, em vez de
        devolver None.

        Por que a diferença existe: _decide() devolve None nesse caso
        de propósito, e isso é uma proteção do MICROFONE — ele escuta
        sem parar, então uma palavra parecida com a wake word no meio
        de conversa ambiente ("véspera…") não pode abrir nada sozinha,
        e exigir um nome de IA logo depois é o que segura isso. No
        relay não existe conversa ambiente: cada mensagem custou um
        toque ou uma frase pra Siri, e o tópico do ntfy é secreto.

        Bug real que isso corrige (CLAUDE.md, limitação 14): o Atalho e
        o rascunho Swift grudam um "over" no FIM de toda mensagem, e é
        justamente esse "over" que faz "só a wake word sozinha" nunca
        acontecer — então "vIsper que horas são over" não abria NADA, e
        sem erro nenhum dos dois lados. Na prática, os dois caminhos de
        iPhone recomendados só funcionavam se a pessoa lembrasse de
        começar dizendo o nome de uma IA.
        """
        decidido = self._decide(transcript)
        if decidido is not None:
            return decidido

        wake = find_trigger_span(transcript, WAKE_WORD, FUZZY_MATCH_THRESHOLD)
        if wake is None:
            return None
        return DEFAULT_AI, trim_for_content(transcript[wake[1]:])

    def preview_complete(self, transcript: str):
        """Qual IA split_complete() abriria — sem abrir nada.

        A trava do relay (RELAY_BLOCKED_AIS) TEM que enxergar o mesmo
        alvo que vai ser aberto de verdade; usar preview() aqui deixaria
        o caminho da DEFAULT_AI passar sem checagem nenhuma."""
        decidido = self.split_complete(transcript)
        return decidido[0] if decidido else None

    def preview(self, transcript: str):
        """
        Qual IA este texto ABRIRIA — sem abrir nada.

        Existe pro relay do iPhone (relay_listener.py) poder recusar
        certos alvos antes de qualquer ação acontecer. Reusa exatamente
        a mesma decisão de route(): duplicar essa lógica num filtro
        separado seria a receita pra ele divergir do roteador e liberar
        justamente o que deveria barrar.

        Retorna o nome da IA, ou None se o texto não abriria nada.
        """
        decision = self._decide(transcript)
        return decision[0] if decision else None

    def _decide(self, transcript: str):
        """
        Toda a decisão, NENHUM efeito colateral. Retorna
        (nome_da_ia, leftover) ou None.

        A ABERTURA (esta função) casa wake word e nome de IA com
        tolerância a erro de transcrição (find_trigger_span com
        config.FUZZY_MATCH_THRESHOLD): "whisper claude" e "vIsper
        cloud" contam como "vIsper claude", porque é assim que o
        Whisper transcreve essas palavras com frequência — e cada erro
        desses fazia o comando falhar calado, o app parecendo surdo. O
        FECHAMENTO (dictation.py) segue EXATO de propósito: abrir por
        engano abre uma aba à toa; fechar por engano manda a mensagem
        pela metade.

        Rede de segurança que mantém o fuzzy seguro no estado ocioso:
        wake word (mesmo aproximada) com conteúdo depois mas NENHUM
        nome de IA continua retornando None — uma palavra parecida com
        a wake word no meio de conversa ambiente ("véspera...") não
        dispara nada sozinha, porque conversa ambiente não costuma
        citar um nome de IA logo depois.
        """
        wake = find_trigger_span(transcript, WAKE_WORD, FUZZY_MATCH_THRESHOLD)
        if wake is None:
            return None

        # Tudo daqui pra baixo trabalha sobre o que vem DEPOIS da wake
        # word, no texto ORIGINAL (o span já vem traduzido pelo mapa de
        # índices de text_utils — dobrar não preserva comprimento).
        rest_original = transcript[wake[1]:]

        # só a wake word, nada depois -> abre a IA padrão. Decide sobre
        # o resto aparado de pontuação — sem isso, "vIsper." (o Whisper
        # adiciona ponto final com frequência) contaria "." como se
        # fosse conteúdo, e o comando mais básico de todos falhava.
        if not trim_for_decision(rest_original):
            return DEFAULT_AI, ""

        # Ganha o apelido que aparece PRIMEIRO na fala; empate na mesma
        # posição vai pro mais COMPRIDO.
        #
        # Antes isso era só "o mais comprido primeiro", sem olhar
        # posição — o que resolvia o caso que motivou a regra ("claude"
        # casando como substring de "claude code") mas quebrava
        # qualquer frase que mencionasse uma segunda IA depois:
        # "vIsper claude e não o perplexity" abria o PERPLEXITY (10
        # letras ganhava de 6) e ainda por cima devolvia leftover
        # vazio, jogando fora a fala inteira. Ordenar por posição
        # devolve o comportamento que config.py sempre documentou ("o
        # primeiro apelido que aparecer decide") e mantém o caso
        # original resolvido: "claude" e "claude code" começam na MESMA
        # posição, então o desempate por comprimento continua valendo
        # e "claude code" continua ganhando.
        best = None  # ((posição, -comprimento), fim_do_span, nome_da_ia)
        for ai_name, triggers in AI_TRIGGERS.items():
            for trigger in triggers:
                span = find_trigger_span(
                    rest_original, trigger, FUZZY_MATCH_THRESHOLD
                )
                if span is None:
                    continue
                key = (span[0], -len(trigger))
                if best is None or key < best[0]:
                    best = (key, span[1], ai_name)

        if best is None:
            return None

        _key, trigger_end, ai_name = best
        # O leftover é fatiado pelo FIM DO SPAN CASADO, não pelo texto
        # do gatilho: com fuzzy, o que está escrito no transcript pode
        # ser "cloud" enquanto o gatilho é "claude" — procurar o
        # gatilho de novo no original nunca acharia nada.
        leftover = trim_for_content(rest_original[trigger_end:])
        return ai_name, leftover

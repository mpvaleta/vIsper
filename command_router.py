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

"""
command_router.py — decide se um texto transcrito deve ABRIR uma IA.

Isso cobre só o "abrir": wake word sozinha abre a IA padrão
(config.DEFAULT_AI), wake word + nome de uma IA (config.AI_TRIGGERS)
abre aquela IA. Qualquer outra coisa dita depois da wake word, que
não seja nome de IA, é ignorada aqui — não faz mais sentido tratar
como comando "manda ver" neste ponto, porque isso só existe DEPOIS
que uma IA já está aberta (ver dictation.py).
"""

from config import WAKE_WORD, DEFAULT_AI, AI_TRIGGERS
from text_utils import contains_word, split_after_word, text_after_word


class CommandRouter:
    def __init__(self, ai_actions: dict):
        """ai_actions: dict {nome_da_ia: função}, vem de actions.AI_ACTIONS"""
        self.ai_actions = ai_actions

    def route(self, transcript: str):
        """
        Processa um texto transcrito. Retorna None se a wake word não
        apareceu ou não bateu com nada reconhecível; senão retorna
        (nome_da_ia, leftover) — `leftover` é o que sobrou depois do
        nome da IA (ou "" se foi só a wake word sozinha, abrindo
        DEFAULT_AI), com capitalização/acento/pontuação ORIGINAIS
        preservados (text_utils.text_after_word()), pra não perder
        conteúdo dito na MESMA respiração que o comando de abrir — ex.:
        "vIsper claude qual é a previsão do tempo" tudo de uma vez.
        Quem chama (dictation.py) decide o que fazer com esse resto.
        """
        if not contains_word(transcript, WAKE_WORD):
            return None

        after_wake = split_after_word(transcript, WAKE_WORD)

        # só a wake word, nada depois -> abre a IA padrão. Usa
        # `after_wake` (aparado de pontuação) pra decidir isso, não o
        # texto original — sem isso, "vIsper." (Whisper adiciona ponto
        # final com frequência) contaria "." como se fosse conteúdo, e
        # esse "." viraria o primeiro item do buffer de ditado.
        if not after_wake:
            self.ai_actions[DEFAULT_AI]()
            return DEFAULT_AI, ""

        # checa os apelidos mais longos primeiro: senão "claude" bate
        # como substring de "claude code" e "claude code" nunca ganha
        all_triggers = [
            (trigger, ai_name)
            for ai_name, triggers in AI_TRIGGERS.items()
            for trigger in triggers
        ]
        all_triggers.sort(key=lambda pair: len(pair[0]), reverse=True)

        for trigger, ai_name in all_triggers:
            if contains_word(after_wake, trigger):
                self.ai_actions[ai_name]()
                # Recalcula sobre o texto ORIGINAL (não `after_wake`,
                # que já veio dobrado/minúsculo/sem pontuação) — o
                # resto pode virar conteúdo real de ditado.
                original_after_wake = text_after_word(transcript, WAKE_WORD)
                leftover = text_after_word(original_after_wake, trigger)
                return ai_name, leftover

        return None

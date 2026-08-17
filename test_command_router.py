"""
Testes dedicados de command_router.py. Até agora esse arquivo só era
exercitado indiretamente (via test_relay_listener.py etc.) — este
arquivo cobre a lógica de roteamento isoladamente, incluindo o
comportamento de casar por palavra inteira/sem acento (text_utils.py)
em vez de substring simples.

route() retorna (nome_da_ia, leftover) em vez de só o nome — leftover
é o que sobrou depois do nome da IA (ou da wake word, no caso
DEFAULT_AI), preservado com capitalização/acento/pontuação originais.
Existe pra não perder conteúdo dito na mesma respiração que o comando
de abrir (ex.: "vIsper claude qual é a previsão do tempo").
"""

import unittest

from command_router import CommandRouter


class CommandRouterTest(unittest.TestCase):
    def _build(self, calls):
        return CommandRouter(
            {
                "claude": lambda: calls.append("claude"),
                "claude_code": lambda: calls.append("claude_code"),
                "chatgpt": lambda: calls.append("chatgpt"),
            }
        )

    def test_so_a_wake_word_abre_a_ia_padrao(self):
        calls = []
        router = self._build(calls)
        result = router.route("vIsper")
        self.assertEqual(result, ("claude", ""))  # DEFAULT_AI em config.py
        self.assertEqual(calls, ["claude"])

    def test_wake_word_mais_nome_abre_a_ia_certa(self):
        calls = []
        router = self._build(calls)
        result = router.route("vIsper chatgpt")
        self.assertEqual(result, ("chatgpt", ""))
        self.assertEqual(calls, ["chatgpt"])

    def test_claude_code_ganha_de_claude_apesar_da_substring(self):
        calls = []
        router = self._build(calls)
        result = router.route("vIsper claude code")
        self.assertEqual(result, ("claude_code", ""))
        self.assertEqual(calls, ["claude_code"])

    def test_apelido_em_portugues_tambem_funciona(self):
        calls = []
        router = self._build(calls)
        result = router.route("vIsper claude código")
        self.assertEqual(result[0], "claude_code")

    def test_sem_wake_word_nao_faz_nada(self):
        calls = []
        router = self._build(calls)
        result = router.route("claude, oi tudo bem")
        self.assertIsNone(result)
        self.assertEqual(calls, [])

    def test_nome_nao_reconhecido_nao_faz_nada(self):
        calls = []
        router = self._build(calls)
        result = router.route("vIsper alguma coisa aleatoria")
        self.assertIsNone(result)
        self.assertEqual(calls, [])

    def test_ignora_maiuscula_minuscula_e_acento(self):
        calls = []
        router = self._build(calls)
        result = router.route("VISPER CLAUDE")
        self.assertEqual(result[0], "claude")

    def test_conteudo_na_mesma_respiracao_e_preservado_como_leftover(self):
        # Regressão: "vIsper claude" + a pergunta de verdade, tudo no
        # mesmo trecho transcrito, sem pausa — antes, só "claude" era
        # usado pra decidir a IA e o resto sumia.
        calls = []
        router = self._build(calls)
        result = router.route("vIsper claude qual é a previsão do tempo hoje?")
        self.assertEqual(result, ("claude", "qual é a previsão do tempo hoje?"))

    def test_leftover_vazio_quando_so_a_wake_word_com_pontuacao(self):
        # "vIsper." (Whisper adiciona ponto final com frequência) tem
        # que abrir DEFAULT_AI com leftover vazio, não com leftover="."
        calls = []
        router = self._build(calls)
        result = router.route("vIsper.")
        self.assertEqual(result, ("claude", ""))

    def test_leftover_depois_do_nome_da_ia_preserva_acento_e_pontuacao(self):
        calls = []
        router = self._build(calls)
        result = router.route("vIsper claude, não esqueça de confirmar!")
        self.assertEqual(result, ("claude", "não esqueça de confirmar!"))

    def test_leftover_vazio_quando_so_o_nome_da_ia(self):
        calls = []
        router = self._build(calls)
        result = router.route("vIsper claude")
        self.assertEqual(result, ("claude", ""))


if __name__ == "__main__":
    unittest.main()

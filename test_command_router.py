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

    def test_ganha_a_ia_citada_primeiro_e_nao_a_de_nome_mais_comprido(self):
        # Regressão: a ordem de checagem era só por COMPRIMENTO do
        # apelido (regra criada pra "claude code" ganhar de "claude").
        # Só que ela também valia entre IAs DIFERENTES, então qualquer
        # frase que citasse uma segunda IA depois abria a errada:
        # "perplexity" (10 letras) ganhava de "claude" (6) mesmo sendo
        # mencionada no fim. Pior: o leftover saía vazio, jogando fora
        # a fala inteira junto.
        calls = []
        router = self._build(calls)
        result = router.route("vIsper claude e não o perplexity")
        self.assertEqual(result, ("claude", "e não o perplexity"))
        self.assertEqual(calls, ["claude"])

    def test_desempate_por_comprimento_continua_valendo_na_mesma_posicao(self):
        # A correção acima não pode reintroduzir o bug original:
        # "claude" e "claude code" começam na MESMA posição, então aí o
        # mais comprido continua ganhando.
        calls = []
        router = self._build(calls)
        self.assertEqual(router.route("vIsper claude code revisa isso")[0], "claude_code")
        self.assertEqual(calls, ["claude_code"])


if __name__ == "__main__":
    unittest.main()


class PreviewTest(unittest.TestCase):
    """
    preview() responde "qual IA isto abriria" SEM abrir. É o que
    permite ao relay do iPhone recusar alvos antes de qualquer ação
    acontecer (ver config.RELAY_BLOCKED_AIS).
    """

    def setUp(self):
        self.abertas = []
        self.router = CommandRouter(
            {
                nome: (lambda n=nome: self.abertas.append(n))
                for nome in ["claude", "claude_code", "chatgpt", "perplexity", "gemini"]
            }
        )

    def test_preview_nao_abre_nada(self):
        alvo = self.router.preview("vIsper claude code faz um deploy")
        self.assertEqual(alvo, "claude_code")
        self.assertEqual(self.abertas, [], "preview() não podia ter aberto nada")

    def test_preview_concorda_com_route(self):
        # Se as duas divergirem, o filtro do relay libera justamente o
        # que deveria barrar — por isso preview() e route() dividem o
        # mesmo _decide() em vez de terem lógicas paralelas.
        for texto in [
            "vIsper claude qual é a previsão",
            "vIsper claude code roda os testes",
            "vIsper",
            "vIsper e não o perplexity",
            "nada disso é comando",
            "vIsper chatgpt resume isso over",
        ]:
            with self.subTest(texto=texto):
                previsto = self.router.preview(texto)
                self.abertas.clear()
                resultado = self.router.route(texto)
                obtido = resultado[0] if resultado else None
                self.assertEqual(previsto, obtido)

    def test_texto_sem_wake_word_nao_preve_nada(self):
        self.assertIsNone(self.router.preview("o claude code é bom"))
        self.assertEqual(self.abertas, [])

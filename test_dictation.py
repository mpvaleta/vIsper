"""
Testes dedicados de dictation.py. Até agora esse arquivo só era
exercitado indiretamente. Cobre a máquina de estados ocioso/ditando,
e especialmente os gatilhos de fechamento novos ("câmbio"/"over"),
incluindo o caso que motivou usar palavra inteira em vez de substring
(over não pode casar dentro de "however"/"discover" no meio do
ditado).
"""

import unittest

from command_router import CommandRouter
from dictation import DictationSession


class DictationSessionTest(unittest.TestCase):
    def _build_session(self, calls, with_sounds=False):
        ai_actions = {"claude": lambda: calls.append("abriu_claude")}
        router = CommandRouter(ai_actions)
        kwargs = {}
        if with_sounds:
            kwargs["on_open"] = lambda: calls.append("som_abriu")
            kwargs["on_send"] = lambda: calls.append("som_mandou")
        return DictationSession(
            router=router,
            paste_action=lambda t: calls.append(("colou", t)),
            send_action=lambda: calls.append("mandou_enter"),
            **kwargs,
        )

    def test_abre_e_entra_em_modo_ditado(self):
        calls = []
        session = self._build_session(calls)
        result = session.handle("vIsper claude")
        self.assertTrue(session.dictating)
        self.assertIn("abriu_claude", calls)
        self.assertIn("abriu claude", result)

    def test_conteudo_vai_pro_buffer_sem_mandar_ainda(self):
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        result = session.handle("isso é o que eu quero ditar")
        self.assertTrue(session.dictating)
        self.assertNotIn("mandou_enter", calls)
        self.assertEqual(result, "ditando…")

    def test_fecha_com_a_wake_word_de_novo(self):
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        session.handle("conteudo do ditado")
        session.handle("vIsper")
        self.assertFalse(session.dictating)
        self.assertIn(("colou", "conteudo do ditado"), calls)
        self.assertIn("mandou_enter", calls)

    def test_fecha_com_cambio(self):
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        session.handle("conteudo em portugues")
        session.handle("câmbio")
        self.assertFalse(session.dictating)
        self.assertIn(("colou", "conteudo em portugues"), calls)

    def test_fecha_com_over(self):
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        session.handle("some content in english")
        session.handle("over")
        self.assertFalse(session.dictating)
        self.assertIn(("colou", "some content in english"), calls)

    def test_over_nao_fecha_por_acidente_dentro_de_however(self):
        # o motivo de tudo isso existir: ditar uma frase com "however"
        # não pode ser confundido com o gatilho de fechamento "over"
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        session.handle("however, I think this works")
        self.assertTrue(session.dictating, "não devia ter fechado — 'over' está dentro de 'however'")
        self.assertNotIn("mandou_enter", calls)
        session.handle("over")  # agora sim fecha, de propósito
        self.assertFalse(session.dictating)

    def test_fecha_sem_conteudo_nao_cola_nem_manda(self):
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        result = session.handle("over")
        self.assertFalse(session.dictating)
        self.assertNotIn("mandou_enter", calls)
        self.assertEqual(result, "cancelado (nada foi ditado)")

    def test_texto_sem_wake_word_enquanto_ocioso_nao_faz_nada(self):
        calls = []
        session = self._build_session(calls)
        result = session.handle("oi, tudo bem?")
        self.assertFalse(session.dictating)
        self.assertIsNone(result)
        self.assertEqual(calls, [])

    def test_conteudo_colado_com_over_no_mesmo_trecho_nao_se_perde(self):
        # Regressão: terminar a frase e já emendar "over" sem pausa faz
        # os dois caírem no MESMO chunk transcrito pelo Whisper. Antes
        # dessa correção, o trecho inteiro era descartado (só o buffer
        # de chamadas anteriores contava) e a sessão "mandava" vazio.
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        result = session.handle("and that is the final summary over")
        self.assertFalse(session.dictating)
        self.assertIn(("colou", "and that is the final summary"), calls)
        self.assertIn("mandou_enter", calls)
        self.assertTrue(result.startswith("mandou:"))

    def test_conteudo_colado_com_cambio_preserva_acento_original(self):
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        session.handle("Não esqueça da reunião de amanhã câmbio")
        self.assertIn(("colou", "Não esqueça da reunião de amanhã"), calls)

    def test_conteudo_colado_combina_com_buffer_de_chamadas_anteriores(self):
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        session.handle("primeira parte")
        session.handle("segunda parte over")
        self.assertIn(("colou", "primeira parte segunda parte"), calls)

    def test_on_open_e_chamado_ao_abrir(self):
        calls = []
        session = self._build_session(calls, with_sounds=True)
        session.handle("vIsper claude")
        self.assertIn("som_abriu", calls)
        self.assertNotIn("som_mandou", calls)

    def test_on_send_e_chamado_ao_mandar_com_conteudo(self):
        calls = []
        session = self._build_session(calls, with_sounds=True)
        session.handle("vIsper claude")
        session.handle("algum conteudo")
        session.handle("over")
        self.assertIn("som_mandou", calls)

    def test_on_send_nao_e_chamado_ao_cancelar_sem_conteudo(self):
        calls = []
        session = self._build_session(calls, with_sounds=True)
        session.handle("vIsper claude")
        session.handle("over")
        self.assertNotIn("som_mandou", calls)

    def test_sem_callbacks_de_som_continua_funcionando_normalmente(self):
        # on_open/on_send são opcionais (None por padrão) — sessão
        # criada sem eles (with_sounds=False, o padrão) não deve
        # quebrar em nenhum dos dois pontos.
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        session.handle("conteudo qualquer")
        session.handle("over")
        self.assertIn(("colou", "conteudo qualquer"), calls)

    def test_conteudo_na_abertura_no_mesmo_trecho_nao_se_perde(self):
        # Regressão simétrica à do fechamento: dizer "vIsper claude" +
        # a pergunta de verdade tudo numa respiração só (mesmo chunk
        # do Whisper) não podia perder o conteúdo — antes, só o nome
        # da IA era usado pra abrir e o resto sumia.
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude qual é a previsão do tempo hoje?")
        self.assertTrue(session.dictating)
        session.handle("over")
        self.assertIn(("colou", "qual é a previsão do tempo hoje?"), calls)

    def test_conteudo_na_abertura_combina_com_falas_seguintes(self):
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude primeira parte")
        session.handle("segunda parte over")
        self.assertIn(("colou", "primeira parte segunda parte"), calls)

    def test_abrir_so_com_o_nome_da_ia_continua_sem_conteudo_no_buffer(self):
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        self.assertEqual(session.buffer, [])

    def test_abrir_e_fechar_no_MESMO_trecho_manda_na_hora(self):
        # Regressão: o pedido inteiro numa respiração só ("vIsper
        # claude <pergunta> over") é o jeito mais natural de usar isso,
        # e era o único caso que nenhuma das duas correções anteriores
        # pegava — elas cuidavam da abertura e do fechamento
        # separadamente. O "over" ia pro buffer como conteúdo: o
        # ditado ficava aberto pra sempre esperando um fechamento que
        # já tinha sido dito, e quando enfim fechasse a palavra "over"
        # ia colada no texto mandado pra IA.
        calls = []
        session = self._build_session(calls)
        result = session.handle("vIsper claude qual é a previsão do tempo over")
        self.assertIn("abriu_claude", calls)
        self.assertFalse(session.dictating, "o 'over' no mesmo trecho tinha que fechar")
        self.assertIn(("colou", "qual é a previsão do tempo"), calls)
        self.assertIn("mandou_enter", calls)
        self.assertIn("abriu claude", result)
        self.assertIn("mandou:", result)

    def test_abrir_e_fechar_no_mesmo_trecho_toca_os_dois_earcons(self):
        calls = []
        session = self._build_session(calls, with_sounds=True)
        session.handle("vIsper claude manda ver nisso câmbio")
        self.assertIn("som_abriu", calls)
        self.assertIn("som_mandou", calls)

    def test_abrir_com_gatilho_de_fechamento_e_nada_mais_nao_manda_vazio(self):
        # "vIsper claude over" abre e fecha sem conteúdo nenhum — não
        # pode colar/mandar string vazia, nem tocar o earcon de envio.
        calls = []
        session = self._build_session(calls, with_sounds=True)
        session.handle("vIsper claude over")
        self.assertFalse(session.dictating)
        self.assertNotIn("mandou_enter", calls)
        self.assertNotIn("som_mandou", calls)
        self.assertEqual([c for c in calls if isinstance(c, tuple)], [])

    def test_fechar_so_com_o_gatilho_continua_sem_conteudo(self):
        # Garante que a correção não inventa conteúdo quando não há
        # nada de verdade antes do gatilho (mesmo caso do teste
        # original test_fecha_sem_conteudo_nao_cola_nem_manda, agora
        # com "vIsper" em vez de "over" fechando).
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        result = session.handle("vIsper")
        self.assertNotIn("mandou_enter", calls)
        self.assertEqual(result, "cancelado (nada foi ditado)")


if __name__ == "__main__":
    unittest.main()

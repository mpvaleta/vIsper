"""
Testa o que config.py CALCULA (não os valores em si, que são dela pra
editar): o vocabulário de comando pro transcritor priorizar.
"""

import unittest

import config


class TranscriptionHotwordsTest(unittest.TestCase):
    def test_contem_o_vocabulario_de_comando_inteiro(self):
        hint = config.transcription_hotwords()
        self.assertIn(config.WAKE_WORD, hint)
        for triggers in config.AI_TRIGGERS.values():
            for trigger in triggers:
                self.assertIn(trigger, hint)
        for close in config.CLOSE_TRIGGERS:
            self.assertIn(close, hint)

    def test_wake_word_vem_primeiro(self):
        # É a palavra mais importante de acertar — inventada, sem ela
        # nada mais acontece.
        hint = config.transcription_hotwords()
        self.assertTrue(hint.startswith(config.WAKE_WORD))

    def test_nao_duplica_palavras(self):
        partes = config.transcription_hotwords().split(", ")
        self.assertEqual(len(partes), len(set(partes)))


class TranscriptionLanguagesTest(unittest.TestCase):
    def test_padrao_lista_os_idiomas_que_a_dona_fala(self):
        # CLAUDE.md: "Comunica em português e inglês" — o padrão
        # reflete isso. setup_visper.py troca em 5 segundos pra quem
        # fala outra coisa.
        self.assertEqual(config.TRANSCRIPTION_LANGUAGES, ["pt", "en"])

    def test_limiar_de_confianca_e_uma_fracao_valida(self):
        self.assertGreaterEqual(config.LANGUAGE_CONFIDENCE_THRESHOLD, 0.0)
        self.assertLessEqual(config.LANGUAGE_CONFIDENCE_THRESHOLD, 1.0)


if __name__ == "__main__":
    unittest.main()

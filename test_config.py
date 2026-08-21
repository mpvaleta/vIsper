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


if __name__ == "__main__":
    unittest.main()

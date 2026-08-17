"""
Testa wake_word_porcupine.py: liga/desliga conforme config, e o
mapeamento do retorno do process() pra True/False (com o motor
Porcupine simulado — sem AccessKey/.ppn reais, ver nota no módulo).
"""

import unittest
from unittest.mock import MagicMock, patch

import wake_word_porcupine as wwp


class PorcupineWakeWordDetectorTest(unittest.TestCase):
    def test_desligado_sem_chave_ou_caminho(self):
        self.assertFalse(
            wwp.PorcupineWakeWordDetector(access_key="", keyword_path="").enabled
        )
        self.assertFalse(
            wwp.PorcupineWakeWordDetector(access_key="abc", keyword_path="").enabled
        )
        self.assertFalse(
            wwp.PorcupineWakeWordDetector(access_key="", keyword_path="/tmp/x.ppn").enabled
        )

    def test_start_recusa_se_desligado(self):
        detector = wwp.PorcupineWakeWordDetector(access_key="", keyword_path="")
        with self.assertRaises(RuntimeError):
            detector.start()

    @patch("wake_word_porcupine.pvporcupine")
    def test_liga_e_detecta_com_motor_simulado(self, mock_pv):
        mock_instance = MagicMock()
        mock_instance.process.side_effect = [-1, -1, 0]  # detecta só no 3º frame
        mock_instance.sample_rate = 16000
        mock_instance.frame_length = 512
        mock_pv.create.return_value = mock_instance

        detector = wwp.PorcupineWakeWordDetector(
            access_key="chave-de-teste", keyword_path="/tmp/fake.ppn"
        )
        self.assertTrue(detector.enabled)
        detector.start()

        self.assertEqual(detector.sample_rate, 16000)
        self.assertEqual(detector.frame_length, 512)

        results = [detector.process_frame([0] * 512) for _ in range(3)]
        self.assertEqual(results, [False, False, True])

        detector.stop()
        mock_instance.delete.assert_called_once()


if __name__ == "__main__":
    unittest.main()

"""
Testa doctor.py: detecta tópico ntfy fraco/óbvio, config incompleta
do Porcupine (só uma das duas chaves), DEFAULT_AI que não existe em
AI_TRIGGERS, e o diagnóstico de dispositivo de entrada (mockando
audio_input pra não depender de mic/PortAudio de verdade). Cada teste
mexe em config.* diretamente e devolve o valor original no final, pra
não vazar estado entre os testes.
"""

import unittest
from unittest.mock import patch

import audio_input
import config
import doctor


class DoctorTest(unittest.TestCase):
    def setUp(self):
        # guarda os valores originais pra restaurar depois de cada teste
        self._original = dict(
            NTFY_TOPIC=config.NTFY_TOPIC,
            PORCUPINE_ACCESS_KEY=config.PORCUPINE_ACCESS_KEY,
            PORCUPINE_KEYWORD_PATH=config.PORCUPINE_KEYWORD_PATH,
            DEFAULT_AI=config.DEFAULT_AI,
        )

    def tearDown(self):
        for key, value in self._original.items():
            setattr(config, key, value)

    def test_topico_ntfy_vazio_e_so_aviso(self):
        config.NTFY_TOPIC = ""
        self.assertEqual(doctor.check_ntfy_topic(), 0)

    def test_topico_ntfy_fraco_falha(self):
        config.NTFY_TOPIC = "visper"
        self.assertEqual(doctor.check_ntfy_topic(), 1)

    def test_topico_ntfy_forte_passa(self):
        config.NTFY_TOPIC = "visper-k3j8fJ29fkalsdKAJ2093jaslkdjKJ"
        self.assertEqual(doctor.check_ntfy_topic(), 0)

    def test_porcupine_vazio_e_so_aviso(self):
        config.PORCUPINE_ACCESS_KEY = ""
        config.PORCUPINE_KEYWORD_PATH = ""
        self.assertEqual(doctor.check_porcupine(), 0)

    def test_porcupine_so_uma_chave_falha(self):
        config.PORCUPINE_ACCESS_KEY = "alguma-chave"
        config.PORCUPINE_KEYWORD_PATH = ""
        self.assertEqual(doctor.check_porcupine(), 1)

    def test_porcupine_arquivo_ppn_inexistente_falha(self):
        config.PORCUPINE_ACCESS_KEY = "alguma-chave"
        config.PORCUPINE_KEYWORD_PATH = "/tmp/isso-nao-existe-de-verdade.ppn"
        self.assertEqual(doctor.check_porcupine(), 1)

    def test_default_ai_invalido_falha(self):
        config.DEFAULT_AI = "ai-que-nao-existe"
        self.assertGreaterEqual(doctor.check_ai_config(), 1)

    def test_default_ai_valido_passa(self):
        config.DEFAULT_AI = "claude"
        self.assertEqual(doctor.check_ai_config(), 0)


class InputDeviceCheckTest(unittest.TestCase):
    """
    check_input_device() é sempre informativo (nunca soma no total de
    problemas — não plugar o mic ainda não é erro de config), então o
    que importa testar é que ele NUNCA explode com nenhuma combinação
    de dispositivos, e reconhece corretamente quando algo bate com
    PREFERRED_INPUT_DEVICES ou não.
    """

    def test_nenhum_dispositivo_conectado_e_so_aviso(self):
        with patch.object(audio_input, "list_input_devices", return_value=[]):
            self.assertEqual(doctor.check_input_device(), 0)

    def test_dispositivo_preferido_detectado_passa(self):
        devices = [(0, "MacBook Pro Microphone"), (1, "DJI Wireless Microphone RX")]
        with patch.object(audio_input, "list_input_devices", return_value=devices), \
             patch.object(audio_input, "guess_preferred_device", return_value=(1, "DJI Wireless Microphone RX", False)):
            self.assertEqual(doctor.check_input_device(), 0)

    def test_fone_bluetooth_detectado_passa(self):
        devices = [(0, "MacBook Pro Microphone"), (1, "WH-1000XM5")]
        with patch.object(audio_input, "list_input_devices", return_value=devices), \
             patch.object(audio_input, "guess_preferred_device", return_value=(1, "WH-1000XM5", True)):
            self.assertEqual(doctor.check_input_device(), 0)

    def test_dispositivos_sem_nenhum_match_e_so_aviso(self):
        devices = [(0, "MacBook Pro Microphone")]
        with patch.object(audio_input, "list_input_devices", return_value=devices), \
             patch.object(audio_input, "guess_preferred_device", return_value=None):
            self.assertEqual(doctor.check_input_device(), 0)

    def test_falha_ao_listar_nao_derruba_o_doctor(self):
        with patch.object(audio_input, "list_input_devices", side_effect=OSError("PortAudio library not found")):
            self.assertEqual(doctor.check_input_device(), 0)


if __name__ == "__main__":
    unittest.main()

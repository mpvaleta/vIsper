"""
Testes de audio_input.py — só a parte que dá pra isolar sem mic de
verdade: list_input_devices() (filtra por max_input_channels) e a
detecção por config.PREFERRED_INPUT_DEVICES (guess_preferred_device(),
classify_device()). Nunca abre um InputStream de verdade.

audio_input.py importa 'sounddevice' de verdade (precisa da lib nativa
PortAudio instalada — brew/apt install portaudio, não só o pacote
Python). Pra esses testes rodarem em QUALQUER ambiente, mesmo sem
PortAudio instalado (ex.: sandbox Linux sem áudio), tenta o import
real primeiro e só cai pro dublê se faltar a lib nativa — mesma
filosofia do resto do projeto: mocka hardware, não reescreve a lógica
por causa dele.
"""

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    import sounddevice  # noqa: F401
except (ImportError, OSError):
    _fake_sd = types.ModuleType("sounddevice")
    _fake_sd.query_devices = MagicMock(return_value=[])
    _fake_sd.InputStream = MagicMock()
    sys.modules["sounddevice"] = _fake_sd

import audio_input  # noqa: E402


def _device(name, max_input_channels=1, **extra):
    d = {"name": name, "max_input_channels": max_input_channels}
    d.update(extra)
    return d


class ListInputDevicesTest(unittest.TestCase):
    def test_so_lista_dispositivo_com_canal_de_entrada(self):
        fake_devices = [
            _device("Mic embutido do MacBook", max_input_channels=1),
            _device("Alto-falantes externos", max_input_channels=0),
            _device("WH-1000XM5", max_input_channels=1),
        ]
        with patch.object(audio_input.sd, "query_devices", return_value=fake_devices):
            result = audio_input.list_input_devices()
        self.assertEqual(result, [(0, "Mic embutido do MacBook"), (2, "WH-1000XM5")])

    def test_lista_vazia_sem_dispositivo_nenhum(self):
        with patch.object(audio_input.sd, "query_devices", return_value=[]):
            self.assertEqual(audio_input.list_input_devices(), [])


class GuessPreferredDeviceTest(unittest.TestCase):
    PREFERRED = [
        {"keywords": ["dji", "wireless microphone rx", "rx"], "bluetooth": False},
        {"keywords": ["wh-1000xm5", "wf-1000xm5", "xm5"], "bluetooth": True},
    ]

    def test_nenhum_dispositivo_retorna_none(self):
        with patch.object(audio_input.sd, "query_devices", return_value=[]):
            self.assertIsNone(audio_input.guess_preferred_device(self.PREFERRED))

    def test_nenhum_bate_retorna_none(self):
        devices = [_device("MacBook Pro Microphone"), _device("Alto-falantes")]
        with patch.object(audio_input.sd, "query_devices", return_value=devices):
            self.assertIsNone(audio_input.guess_preferred_device(self.PREFERRED))

    def test_detecta_dji_pelo_nome_usual(self):
        devices = [_device("MacBook Pro Microphone"), _device("DJI Wireless Microphone RX")]
        with patch.object(audio_input.sd, "query_devices", return_value=devices):
            result = audio_input.guess_preferred_device(self.PREFERRED)
        self.assertEqual(result, (1, "DJI Wireless Microphone RX", False))

    def test_detecta_sony_xm5_como_bluetooth(self):
        devices = [_device("MacBook Pro Microphone"), _device("WH-1000XM5")]
        with patch.object(audio_input.sd, "query_devices", return_value=devices):
            result = audio_input.guess_preferred_device(self.PREFERRED)
        self.assertEqual(result, (1, "WH-1000XM5", True))

    def test_detecta_earbuds_sony_wf_1000xm5_tambem(self):
        devices = [_device("WF-1000XM5")]
        with patch.object(audio_input.sd, "query_devices", return_value=devices):
            result = audio_input.guess_preferred_device(self.PREFERRED)
        self.assertEqual(result, (0, "WF-1000XM5", True))

    def test_nome_pareado_customizado_ainda_bate_por_substring(self):
        # macOS às vezes usa o nome que a pessoa deu ao parear, não só
        # o nome de fábrica — "xm5" continua aparecendo dentro dele.
        devices = [_device("Fone do Marcos (WH-1000XM5)")]
        with patch.object(audio_input.sd, "query_devices", return_value=devices):
            result = audio_input.guess_preferred_device(self.PREFERRED)
        self.assertEqual(result, (0, "Fone do Marcos (WH-1000XM5)", True))

    def test_ignora_maiuscula_minuscula(self):
        devices = [_device("wh-1000xm5")]
        with patch.object(audio_input.sd, "query_devices", return_value=devices):
            result = audio_input.guess_preferred_device(self.PREFERRED)
        self.assertEqual(result, (0, "wh-1000xm5", True))

    def test_dji_ganha_do_sony_quando_os_dois_estao_conectados(self):
        # DJI vem primeiro em PREFERRED_INPUT_DEVICES (mic dedicado,
        # sem o efeito colateral de qualidade do Bluetooth) — ver
        # config.py pro raciocínio completo.
        devices = [_device("WH-1000XM5"), _device("DJI Wireless Microphone RX")]
        with patch.object(audio_input.sd, "query_devices", return_value=devices):
            result = audio_input.guess_preferred_device(self.PREFERRED)
        self.assertEqual(result, (1, "DJI Wireless Microphone RX", False))

    def test_usa_config_preferred_input_devices_por_padrao(self):
        # Sem passar `preferred`, deve ler de config.PREFERRED_INPUT_DEVICES
        # de verdade — confere que o config real do projeto já reconhece
        # Sony XM5 de fábrica, sem precisar de override em teste.
        devices = [_device("WH-1000XM5")]
        with patch.object(audio_input.sd, "query_devices", return_value=devices):
            result = audio_input.guess_preferred_device()
        self.assertIsNotNone(result)
        self.assertTrue(result[2])  # is_bluetooth


class LabelDevicesTest(unittest.TestCase):
    def test_nomes_unicos_ficam_sem_alteracao(self):
        devices = [(0, "MacBook Pro Microphone"), (1, "WH-1000XM5")]
        self.assertEqual(
            audio_input.label_devices(devices),
            [(0, "MacBook Pro Microphone", "MacBook Pro Microphone"), (1, "WH-1000XM5", "WH-1000XM5")],
        )

    def test_nomes_duplicados_ganham_indice_no_rotulo(self):
        # O bug que isso corrige: sem desambiguar, rumps (indexa o
        # submenu pelo título) faria o segundo "WH-1000XM5" sumir do
        # menu — não aparecia, não dava pra escolher, sem erro nenhum.
        devices = [(0, "WH-1000XM5"), (1, "WH-1000XM5")]
        result = audio_input.label_devices(devices)
        labels = [label for _i, _n, label in result]
        self.assertEqual(len(set(labels)), 2)  # os dois rótulos ficam ÚNICOS
        self.assertIn("WH-1000XM5 (índice 0)", labels)
        self.assertIn("WH-1000XM5 (índice 1)", labels)

    def test_nome_original_preservado_mesmo_com_rotulo_desambiguado(self):
        # Seleção/persistência usam o NOME (2º item da tupla), não o
        # rótulo — precisa continuar sendo o nome puro, sem o sufixo.
        devices = [(0, "WH-1000XM5"), (1, "WH-1000XM5")]
        result = audio_input.label_devices(devices)
        for _index, name, _label in result:
            self.assertEqual(name, "WH-1000XM5")

    def test_lista_vazia(self):
        self.assertEqual(audio_input.label_devices([]), [])


class DeviceChoicePersistenceTest(unittest.TestCase):
    """
    load_saved_device_name()/save_device_choice() tocam disco de
    verdade (não são coisa que faz sentido mockar — o comportamento
    QUE IMPORTA é ler/escrever um arquivo real). Cada teste aponta
    audio_input.DEVICE_STATE_PATH pra dentro de um diretório
    temporário próprio, nunca pro ~/Library/Application Support real.
    """

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        patcher = patch.object(
            audio_input, "DEVICE_STATE_PATH", Path(self._tmpdir.name) / "vIsper" / "device.json"
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_nada_salvo_ainda_retorna_none(self):
        self.assertIsNone(audio_input.load_saved_device_name())

    def test_salva_e_le_de_volta(self):
        audio_input.save_device_choice("WH-1000XM5")
        self.assertEqual(audio_input.load_saved_device_name(), "WH-1000XM5")

    def test_salvar_none_limpa_a_escolha(self):
        audio_input.save_device_choice("WH-1000XM5")
        audio_input.save_device_choice(None)
        self.assertIsNone(audio_input.load_saved_device_name())

    def test_cria_o_diretorio_pai_se_nao_existir(self):
        self.assertFalse(audio_input.DEVICE_STATE_PATH.parent.exists())
        audio_input.save_device_choice("DJI Wireless Microphone RX")
        self.assertTrue(audio_input.DEVICE_STATE_PATH.exists())

    def test_arquivo_corrompido_retorna_none_em_vez_de_lancar(self):
        audio_input.DEVICE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        audio_input.DEVICE_STATE_PATH.write_text("isso não é json{{{")
        self.assertIsNone(audio_input.load_saved_device_name())

    def test_falha_ao_salvar_nao_propaga(self):
        # Simula "sem permissão de escrita" — save_device_choice() não
        # pode derrubar o clique no menu por causa disso.
        with patch.object(Path, "write_text", side_effect=OSError("sem permissão")):
            try:
                audio_input.save_device_choice("WH-1000XM5")
            except OSError:
                self.fail("save_device_choice() não devia propagar OSError")


class ResolveDeviceByNameTest(unittest.TestCase):
    def test_encontra_pelo_nome_exato(self):
        devices = [_device("MacBook Pro Microphone"), _device("WH-1000XM5")]
        with patch.object(audio_input.sd, "query_devices", return_value=devices):
            self.assertEqual(audio_input.resolve_device_by_name("WH-1000XM5"), 1)

    def test_nome_nao_encontrado_retorna_none(self):
        devices = [_device("MacBook Pro Microphone")]
        with patch.object(audio_input.sd, "query_devices", return_value=devices):
            self.assertIsNone(audio_input.resolve_device_by_name("WH-1000XM5"))

    def test_indice_muda_quando_outro_dispositivo_some_da_lista(self):
        # O cenário real que motivou essa função: um device escolhido
        # manualmente no índice 1 pode passar a ser o índice 0 depois
        # que outro dispositivo (índice 0 antigo) desconecta. Resolver
        # de novo pelo NOME pega o índice atual certo, não o antigo.
        before = [_device("DJI Wireless Microphone RX"), _device("WH-1000XM5")]
        with patch.object(audio_input.sd, "query_devices", return_value=before):
            self.assertEqual(audio_input.resolve_device_by_name("WH-1000XM5"), 1)

        after_dji_desconectou = [_device("WH-1000XM5")]
        with patch.object(audio_input.sd, "query_devices", return_value=after_dji_desconectou):
            self.assertEqual(audio_input.resolve_device_by_name("WH-1000XM5"), 0)


class ClassifyDeviceTest(unittest.TestCase):
    PREFERRED = GuessPreferredDeviceTest.PREFERRED

    def test_dji_nao_e_bluetooth(self):
        self.assertFalse(audio_input.classify_device("DJI Wireless Microphone RX", self.PREFERRED))

    def test_sony_xm5_e_bluetooth(self):
        self.assertTrue(audio_input.classify_device("WH-1000XM5", self.PREFERRED))

    def test_dispositivo_desconhecido_nao_e_bluetooth_por_padrao(self):
        # Só avisamos qualidade quando temos certeza — nome que não
        # bate com nenhum grupo conhecido (ex.: mic embutido do Mac)
        # não deve disparar o aviso de Bluetooth.
        self.assertFalse(audio_input.classify_device("MacBook Pro Microphone", self.PREFERRED))

    def test_ignora_maiuscula_minuscula(self):
        self.assertTrue(audio_input.classify_device("Wh-1000Xm5", self.PREFERRED))


if __name__ == "__main__":
    unittest.main()

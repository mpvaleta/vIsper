"""
Testes de main.py — a parte que dá pra isolar sem Mac, sem barra de
menu e sem microfone: a escolha de dispositivo (automática × manual ×
escolha salva de outra execução) e os guards de "Iniciar escuta".

main.py importa rumps (AppKit) e faster_whisper (modelo pesado), que
não existem — nem fazem sentido — num sandbox Linux. Mesma filosofia
do resto do projeto: MOCKA o hardware/framework, não reescreve a
lógica por causa dele. Os dublês abaixo imitam só o pedacinho da API
que main.py usa de verdade (App, MenuItem.clear()/.add()/.state/.title,
clicked, alert, notification).

O que isso NÃO cobre, e continua só validável num Mac de verdade: o
menu renderizar mesmo, o AppKit aceitar título mutável, e o áudio.
"""

import sys
import types
import unittest
from unittest.mock import MagicMock, patch


# ----------------------------------------------------------------------
# Dublês instalados ANTES de importar main.py (os decoradores
# @rumps.clicked rodam na definição da classe, não dá pra adiar).
# ----------------------------------------------------------------------
class FakeMenuItem:
    def __init__(self, title, callback=None):
        self.title = title
        self.callback = callback
        self.state = 0
        self.items = []

    def clear(self):
        self.items = []

    def add(self, item):
        self.items.append(item)


class FakeApp:
    def __init__(self, name, icon=None, quit_button=None):
        self.name = name
        self.menu = []


def _install_fakes():
    if "sounddevice" not in sys.modules:
        fake_sd = types.ModuleType("sounddevice")
        fake_sd.query_devices = MagicMock(return_value=[])
        fake_sd.InputStream = MagicMock()
        sys.modules["sounddevice"] = fake_sd

    if "rumps" not in sys.modules:
        fake_rumps = types.ModuleType("rumps")
        fake_rumps.App = FakeApp
        fake_rumps.MenuItem = FakeMenuItem
        fake_rumps.clicked = lambda *_args, **_kwargs: (lambda func: func)
        fake_rumps.alert = MagicMock()
        fake_rumps.notification = MagicMock()
        sys.modules["rumps"] = fake_rumps

    if "faster_whisper" not in sys.modules:
        fake_fw = types.ModuleType("faster_whisper")
        fake_fw.WhisperModel = MagicMock()
        sys.modules["faster_whisper"] = fake_fw


_install_fakes()

import main  # noqa: E402


def _build_app(saved_device_name=None, devices=None):
    """VisperApp com o disco (escolha salva) e a lista de dispositivos
    controlados pelo teste — nunca toca no ~/Library de verdade."""
    devices = devices if devices is not None else []
    with patch("main.load_saved_device_name", return_value=saved_device_name), patch(
        "main.list_input_devices", return_value=devices
    ):
        return main.VisperApp()


class DispositivoSalvoTest(unittest.TestCase):
    def test_escolha_salva_de_fone_bluetooth_e_reclassificada_ao_abrir(self):
        # Regressão: só _make_pick_device() (o clique no menu) sabia
        # dizer se o dispositivo é Bluetooth, e isso não sobrevive a
        # fechar o app — só o NOME é persistido. Ao reabrir o vIsper
        # com o fone já escolhido, device_is_bluetooth ficava False pra
        # sempre e o aviso de qualidade de áudio nunca mais aparecia,
        # justo no caso em que ele é mais útil (fone escolhido de
        # propósito, sessão após sessão).
        app = _build_app(
            saved_device_name="WH-1000XM5", devices=[(0, "WH-1000XM5")]
        )
        self.assertTrue(app.device_manual)
        self.assertEqual(app.device_name, "WH-1000XM5")
        self.assertTrue(app.device_is_bluetooth)

    def test_escolha_salva_de_mic_com_fio_nao_marca_bluetooth(self):
        app = _build_app(
            saved_device_name="DJI Wireless Microphone RX",
            devices=[(0, "DJI Wireless Microphone RX")],
        )
        self.assertTrue(app.device_manual)
        self.assertFalse(app.device_is_bluetooth)

    def test_sem_escolha_salva_comeca_em_modo_automatico(self):
        app = _build_app(saved_device_name=None, devices=[(0, "MacBook Pro Microphone")])
        self.assertFalse(app.device_manual)
        self.assertIsNone(app.device_name)
        self.assertFalse(app.device_is_bluetooth)

    def test_resolve_device_reclassifica_a_escolha_manual(self):
        # _resolve_device() é o único ponto por onde uma escolha manual
        # restaurada passa antes de abrir o stream — tem que deixar
        # device_is_bluetooth certo mesmo se __init__ não tivesse.
        app = _build_app(saved_device_name="WH-1000XM5", devices=[(3, "WH-1000XM5")])
        app.device_is_bluetooth = False  # simula o estado errado de antes
        with patch("main.resolve_device_by_name", return_value=3):
            self.assertTrue(app._resolve_device())
        self.assertEqual(app.device_index, 3)
        self.assertTrue(app.device_is_bluetooth)

    def test_resolve_device_falha_quando_o_dispositivo_salvo_sumiu(self):
        app = _build_app(saved_device_name="WH-1000XM5")
        with patch("main.resolve_device_by_name", return_value=None):
            self.assertFalse(app._resolve_device())


class IniciarEscutaTest(unittest.TestCase):
    def setUp(self):
        main.rumps.alert.reset_mock()
        main.rumps.notification.reset_mock()

    def test_aviso_de_dispositivo_sumido_fala_do_escolhido_manualmente(self):
        # A mensagem antiga dizia "nenhum microfone reconhecido
        # automaticamente... escolha manualmente no menu" mesmo quando
        # a pessoa JÁ tinha escolhido e o aparelho é que estava
        # desconectado — mandava fazer de novo o que já estava feito.
        app = _build_app(saved_device_name="WH-1000XM5")
        with patch("main.resolve_device_by_name", return_value=None):
            app.start_listening(None)
        main.rumps.alert.assert_called_once()
        mensagem = main.rumps.alert.call_args[0][0]
        self.assertIn("WH-1000XM5", mensagem)
        self.assertFalse(app.listening)

    def test_aviso_de_auto_deteccao_quando_nao_ha_escolha_manual(self):
        app = _build_app(saved_device_name=None)
        with patch("main.guess_preferred_device", return_value=None):
            app.start_listening(None)
        main.rumps.alert.assert_called_once()
        self.assertIn(
            "automaticamente", main.rumps.alert.call_args[0][0]
        )
        self.assertFalse(app.listening)

    def test_nao_abre_uma_segunda_thread_com_a_anterior_ainda_viva(self):
        # Regressão: "Parar escuta" só baixa a flag; a thread antiga
        # ainda pode estar dentro de um stream.read() de até
        # chunk_seconds. Clicar Parar e Iniciar em seguida passava pelo
        # guard `if self.listening` (já era False) e abria uma SEGUNDA
        # thread de escuta — duas transcrições paralelas alimentando o
        # mesmo DictationSession.
        app = _build_app(saved_device_name=None, devices=[(0, "DJI Mic")])
        thread_antiga = MagicMock()
        thread_antiga.is_alive.return_value = True
        app._listen_thread = thread_antiga

        with patch("main.threading.Thread") as fake_thread:
            app.start_listening(None)

        fake_thread.assert_not_called()
        self.assertFalse(app.listening)
        main.rumps.notification.assert_called_once()

    def test_inicia_normalmente_quando_a_thread_anterior_ja_terminou(self):
        app = _build_app(saved_device_name=None, devices=[(0, "DJI Mic")])
        thread_antiga = MagicMock()
        thread_antiga.is_alive.return_value = False
        app._listen_thread = thread_antiga

        with patch(
            "main.guess_preferred_device", return_value=(0, "DJI Mic", False)
        ), patch("main.threading.Thread") as fake_thread:
            app.start_listening(None)

        fake_thread.assert_called_once()
        self.assertTrue(app.listening)

    def test_avisa_qualidade_bluetooth_ao_iniciar_com_fone(self):
        app = _build_app(saved_device_name="WH-1000XM5", devices=[(0, "WH-1000XM5")])
        with patch("main.resolve_device_by_name", return_value=0), patch(
            "main.threading.Thread"
        ):
            app.start_listening(None)
        main.rumps.notification.assert_called_once()
        titulo = main.rumps.notification.call_args[0][1]
        self.assertIn("Bluetooth", titulo)


class MenuDeMicrofoneTest(unittest.TestCase):
    def test_checkmark_marca_o_dispositivo_salvo_logo_no_primeiro_menu(self):
        # O checkmark compara por NOME, não índice: logo depois de
        # carregar a escolha salva o índice ainda é None.
        app = _build_app(
            saved_device_name="WH-1000XM5",
            devices=[(0, "MacBook Pro Microphone"), (1, "WH-1000XM5")],
        )
        with patch(
            "main.list_input_devices",
            return_value=[(0, "MacBook Pro Microphone"), (1, "WH-1000XM5")],
        ):
            app._rebuild_mic_menu()
        estados = {item.title: bool(item.state) for item in app.mic_menu.items}
        self.assertFalse(estados["Detectar automaticamente"])
        self.assertFalse(estados["MacBook Pro Microphone"])
        self.assertTrue(estados["WH-1000XM5"])

    def test_voltar_pro_automatico_esquece_a_escolha_e_o_bluetooth(self):
        app = _build_app(saved_device_name="WH-1000XM5", devices=[(0, "WH-1000XM5")])
        with patch("main.save_device_choice") as fake_save, patch(
            "main.list_input_devices", return_value=[(0, "WH-1000XM5")]
        ):
            app._pick_auto(None)
        fake_save.assert_called_once_with(None)
        self.assertFalse(app.device_manual)
        self.assertIsNone(app.device_name)
        self.assertFalse(app.device_is_bluetooth)


if __name__ == "__main__":
    unittest.main()

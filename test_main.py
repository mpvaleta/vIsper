"""
Testes de main.py — a parte que dá pra isolar sem Mac, sem barra de
menu e sem microfone: escolha de dispositivo (automática × manual ×
salva × padrão do sistema), os guards de "Start listening", o
carregamento do modelo em segundo plano, o estado visível na barra de
menu, e a notificação à prova de falha.

main.py importa rumps (AppKit) e faster_whisper (modelo pesado), que
não existem — nem fazem sentido — num sandbox Linux. Mesma filosofia
do resto do projeto: MOCKA o hardware/framework, não reescreve a
lógica por causa dele. Os dublês abaixo imitam só o pedacinho da API
que main.py usa de verdade.

O que isso NÃO cobre, e continua só validável num Mac de verdade: o
menu renderizar mesmo, o AppKit aceitar título mutável, o emoji do
estado ficar legível na barra, e o áudio.
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
    """
    Imita o rumps.MenuItem real com uma peculiaridade de TIMING que
    mordeu de verdade: o NSMenu interno do submenu (`_menu` no rumps
    real) só é criado no primeiro `.add()` — antes disso é `None`, e
    `.clear()` (que chama `self._menu.removeAllItems()`) explode com
    AttributeError.

    A primeira versão deste dublê não reproduzia isso (`clear()` só
    fazia `self.items = []`, incondicional) — por isso os 244 testes
    passavam com main.py quebrado: main._rebuild_mic_menu() chamava
    `.clear()` ANTES de qualquer `.add()` na primeiríssima chamada
    (vinda do __init__), e isso só apareceu rodando num Mac de
    verdade. Modelar a peculiaridade aqui é o que faz esse bug — e
    qualquer regressão dele — aparecer de novo em CI, sem precisar de
    hardware real.
    """

    def __init__(self, title, callback=None):
        self.title = title
        self.callback = callback
        self.state = 0
        self.items = []
        self._menu_created = False

    def clear(self):
        if not self._menu_created:
            raise AttributeError(
                "'NoneType' object has no attribute 'removeAllItems'"
            )
        self.items = []

    def add(self, item):
        self._menu_created = True
        self.items.append(item)


class FakeApp:
    def __init__(self, name, icon=None, quit_button=None):
        # rumps.App guarda o nome como título da barra de menu, e
        # main._set_state() troca esse título pra comunicar estado —
        # então o dublê precisa ter o atributo desde o começo.
        self.title = name
        self.name = name
        self.menu = []


class FakeWindowResponse:
    def __init__(self, clicked=1, text=""):
        self.clicked = clicked
        self.text = text


def _install_fakes():
    if "sounddevice" not in sys.modules:
        fake_sd = types.ModuleType("sounddevice")
        fake_sd.query_devices = MagicMock(return_value=[])
        fake_sd.InputStream = MagicMock()
        fake_sd.default = types.SimpleNamespace(device=(0, 1))
        sys.modules["sounddevice"] = fake_sd

    if "rumps" not in sys.modules:
        fake_rumps = types.ModuleType("rumps")
        fake_rumps.App = FakeApp
        fake_rumps.MenuItem = FakeMenuItem
        fake_rumps.clicked = lambda *_args, **_kwargs: (lambda func: func)
        fake_rumps.alert = MagicMock()
        fake_rumps.notification = MagicMock()
        fake_rumps.Window = MagicMock()
        fake_rumps.quit_application = MagicMock()
        sys.modules["rumps"] = fake_rumps

    if "faster_whisper" not in sys.modules:
        fake_fw = types.ModuleType("faster_whisper")
        fake_fw.WhisperModel = MagicMock()
        sys.modules["faster_whisper"] = fake_fw


_install_fakes()

import main  # noqa: E402


def _build_app(saved_device_name=None, devices=None, load_model=False):
    """
    VisperApp com o disco (escolha salva) e a lista de dispositivos
    controlados pelo teste — nunca toca no ~/Library de verdade.

    Por padrão a thread que carrega o modelo NÃO roda: ela é assíncrona
    e deixaria os testes correndo contra ela. Os testes que se importam
    com o modelo chamam _load_model() na mão.
    """
    devices = devices if devices is not None else []
    with patch("main.load_saved_device_name", return_value=saved_device_name), patch(
        "main.list_input_devices", return_value=devices
    ), patch("main.threading.Thread") as fake_thread:
        app = main.VisperApp()
        if load_model:
            app._load_model()
    app._thread_ctor = fake_thread
    return app


class DispositivoSalvoTest(unittest.TestCase):
    def test_escolha_salva_de_fone_bluetooth_e_reclassificada_ao_abrir(self):
        # Regressão: só _make_pick_device() (o clique no menu) sabia
        # dizer se o dispositivo é Bluetooth, e isso não sobrevive a
        # fechar o app — só o NOME é persistido. Ao reabrir o vIsper
        # com o fone já escolhido, device_is_bluetooth ficava False pra
        # sempre e o aviso de qualidade de áudio nunca mais aparecia,
        # justo no caso em que ele é mais útil (fone escolhido de
        # propósito, sessão após sessão).
        app = _build_app(saved_device_name="WH-1000XM5", devices=[(0, "WH-1000XM5")])
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


class MicrofonePadraoTest(unittest.TestCase):
    """
    Sem o DJI nem o Sony por perto, o vIsper tem que usar o microfone
    embutido do Mac em vez de recusar a escutar. Antes, guess_preferred
    devolvia None, "Start listening" mostrava um alerta e nada
    acontecia — dando a impressão de app quebrado com um mic perfeito
    ali o tempo todo.
    """

    def test_cai_no_padrao_do_sistema_quando_nenhum_preferido_esta_por_perto(self):
        app = _build_app(saved_device_name=None)
        with patch("main.guess_preferred_device", return_value=None), patch(
            "main.default_input_device",
            return_value=(2, "MacBook Pro Microphone", False),
        ):
            self.assertTrue(app._resolve_device())
        self.assertEqual(app.device_index, 2)
        self.assertEqual(app.device_name, "MacBook Pro Microphone")

    def test_preferido_ainda_ganha_do_padrao(self):
        app = _build_app(saved_device_name=None)
        with patch(
            "main.guess_preferred_device", return_value=(5, "DJI Mic RX", False)
        ), patch("main.default_input_device") as fake_padrao:
            self.assertTrue(app._resolve_device())
        fake_padrao.assert_not_called()
        self.assertEqual(app.device_name, "DJI Mic RX")

    def test_sem_nenhum_microfone_na_maquina_falha(self):
        app = _build_app(saved_device_name=None)
        with patch("main.guess_preferred_device", return_value=None), patch(
            "main.default_input_device", return_value=None
        ):
            self.assertFalse(app._resolve_device())


class CarregarModeloTest(unittest.TestCase):
    """
    O modelo do Whisper baixa ~150 MB na primeira execução. Carregar
    isso no __init__ deixava o app minutos sem ícone nenhum, e qualquer
    falha (sem internet, download cortado) matava o processo ANTES do
    ícone existir — num .app, sem Terminal, isso é um app que
    simplesmente não abre e não explica nada.
    """

    def setUp(self):
        main.rumps.alert.reset_mock()
        main.rumps.notification.reset_mock()

    def test_o_icone_existe_antes_do_modelo_carregar(self):
        app = _build_app()
        self.assertIsNone(app.model)
        self.assertEqual(app.title, main.STATE_GLYPHS["loading"])

    def test_modelo_carregado_deixa_o_app_pronto(self):
        app = _build_app(load_model=True)
        self.assertIsNotNone(app.model)
        self.assertIsNone(app.model_error)
        self.assertEqual(app.title, main.STATE_GLYPHS["stopped"])

    def test_falha_ao_carregar_guarda_o_motivo_e_nao_levanta(self):
        app = _build_app()
        with patch("main.WhisperModel", side_effect=OSError("sem internet")):
            app._load_model()  # não pode propagar: mataria a thread calada
        self.assertIsNone(app.model)
        self.assertIn("sem internet", app.model_error)
        self.assertEqual(app.title, main.STATE_GLYPHS["error"])

    def test_iniciar_antes_do_modelo_explica_em_vez_de_falhar(self):
        app = _build_app()
        app.start_listening(None)
        self.assertFalse(app.listening)
        main.rumps.notification.assert_called_once()
        self.assertIn("speech model", main.rumps.notification.call_args[0][2])

    def test_iniciar_depois_de_falhar_repete_o_motivo_exato(self):
        # A notificação some em segundos e ela pode nem estar olhando.
        # Quando finalmente clicar, o motivo tem que reaparecer.
        app = _build_app()
        with patch("main.WhisperModel", side_effect=OSError("sem internet")):
            app._load_model()
        main.rumps.alert.reset_mock()
        app.start_listening(None)
        main.rumps.alert.assert_called_once()
        self.assertIn("sem internet", main.rumps.alert.call_args[0][0])


class NotificacaoTest(unittest.TestCase):
    """
    rumps.notification() exige um bundle com identificador — rodando
    por `python3 main.py`, que é exatamente como ela vai testar da
    primeira vez, ele levanta RuntimeError. Como isso é chamado de
    dentro do loop de ditado, a exceção derrubava a thread de escuta
    inteira: o app parava de funcionar por causa do MECANISMO DE AVISO,
    não do que ele avisa.
    """

    def test_notify_engole_a_falha_de_bundle(self):
        with patch.object(
            main.rumps,
            "notification",
            side_effect=RuntimeError("Code signing/bundle identifier not found"),
        ), patch("builtins.print"):  # o print é o fallback, não saída de teste
            main.notify("vIsper", "Status", "algo aconteceu")  # não pode levantar

    def test_notify_cai_pro_stdout_quando_falha(self):
        with patch.object(
            main.rumps, "notification", side_effect=RuntimeError("sem bundle")
        ), patch("builtins.print") as fake_print:
            main.notify("vIsper", "Status", "mandou ver")
        fake_print.assert_called_once()
        self.assertIn("mandou ver", fake_print.call_args[0][0])

    def test_notify_usa_rumps_quando_da_certo(self):
        with patch.object(main.rumps, "notification") as fake_notif:
            main.notify("vIsper", "Status", "ok")
        fake_notif.assert_called_once_with("vIsper", "Status", "ok")


class EstadoNaBarraTest(unittest.TestCase):
    """
    O ícone é o único retorno que não some sozinho. Antes o título era
    fixo e o único feedback era notificação — não dava pra responder
    "ele está me ouvindo agora?" sem falar uma frase de teste e torcer.
    """

    def test_abrir_ditado_pinta_de_ditando(self):
        app = _build_app(load_model=True)
        with patch.object(main.actions, "play_sound"):
            app._on_dictation_open()
        self.assertEqual(app.title, main.STATE_GLYPHS["dictating"])

    def test_mandar_pinta_de_enviado(self):
        app = _build_app(load_model=True)
        with patch.object(main.actions, "play_sound"):
            app._on_dictation_send()
        self.assertEqual(app.title, main.STATE_GLYPHS["sent"])

    def test_parar_escuta_volta_pro_parado(self):
        app = _build_app(load_model=True)
        app.listening = True
        app._set_state("listening")
        app.stop_listening(None)
        self.assertFalse(app.listening)
        self.assertEqual(app.title, main.STATE_GLYPHS["stopped"])

    def test_o_que_foi_ouvido_aparece_no_menu(self):
        # A falha mais confusa deste app é a wake word ser transcrita
        # errada; sem isso, "não me ouve" e "ouviu mas escreveu outra
        # coisa" são indistinguíveis.
        app = _build_app(load_model=True)
        app._set_heard("vísper cláudio qual é a previsão")
        self.assertIn("vísper cláudio", app.heard_item.title)

    def test_texto_longo_e_cortado_no_menu(self):
        app = _build_app(load_model=True)
        app._set_heard("palavra " * 40)
        self.assertLessEqual(len(app.heard_item.title), 60)

    def test_sem_nada_ouvido_mostra_travessao(self):
        app = _build_app(load_model=True)
        app._set_heard("")
        self.assertEqual(app.heard_item.title, "Heard: —")


class IniciarEscutaTest(unittest.TestCase):
    def setUp(self):
        main.rumps.alert.reset_mock()
        main.rumps.notification.reset_mock()

    def test_aviso_de_dispositivo_sumido_fala_do_escolhido_manualmente(self):
        # A mensagem antiga dizia "nenhum microfone reconhecido
        # automaticamente... escolha manualmente no menu" mesmo quando
        # a pessoa JÁ tinha escolhido e o aparelho é que estava
        # desconectado — mandava fazer de novo o que já estava feito.
        app = _build_app(saved_device_name="WH-1000XM5", load_model=True)
        with patch("main.resolve_device_by_name", return_value=None):
            app.start_listening(None)
        main.rumps.alert.assert_called_once()
        mensagem = main.rumps.alert.call_args[0][0]
        self.assertIn("WH-1000XM5", mensagem)
        self.assertFalse(app.listening)

    def test_aviso_quando_a_maquina_nao_tem_microfone_nenhum(self):
        app = _build_app(saved_device_name=None, load_model=True)
        with patch("main.guess_preferred_device", return_value=None), patch(
            "main.default_input_device", return_value=None
        ):
            app.start_listening(None)
        main.rumps.alert.assert_called_once()
        self.assertIn("microphone", main.rumps.alert.call_args[0][0].lower())
        self.assertFalse(app.listening)

    def test_nao_abre_uma_segunda_thread_com_a_anterior_ainda_viva(self):
        # Regressão: "Stop listening" só baixa a flag; a thread antiga
        # ainda pode estar dentro de um stream.read() de até
        # chunk_seconds. Clicar Stop e Start em seguida passava pelo
        # guard `if self.listening` (já era False) e abria uma SEGUNDA
        # thread de escuta — duas transcrições paralelas alimentando o
        # mesmo DictationSession.
        app = _build_app(
            saved_device_name=None, devices=[(0, "DJI Mic")], load_model=True
        )
        thread_antiga = MagicMock()
        thread_antiga.is_alive.return_value = True
        app._listen_thread = thread_antiga

        with patch("main.threading.Thread") as fake_thread:
            app.start_listening(None)

        fake_thread.assert_not_called()
        self.assertFalse(app.listening)
        main.rumps.notification.assert_called_once()

    def test_inicia_normalmente_quando_a_thread_anterior_ja_terminou(self):
        app = _build_app(
            saved_device_name=None, devices=[(0, "DJI Mic")], load_model=True
        )
        thread_antiga = MagicMock()
        thread_antiga.is_alive.return_value = False
        app._listen_thread = thread_antiga

        with patch(
            "main.guess_preferred_device", return_value=(0, "DJI Mic", False)
        ), patch("main.threading.Thread") as fake_thread:
            app.start_listening(None)

        fake_thread.assert_called_once()
        self.assertTrue(app.listening)
        self.assertEqual(app.title, main.STATE_GLYPHS["listening"])

    def test_avisa_qualidade_bluetooth_ao_iniciar_com_fone(self):
        app = _build_app(
            saved_device_name="WH-1000XM5", devices=[(0, "WH-1000XM5")], load_model=True
        )
        with patch("main.resolve_device_by_name", return_value=0), patch(
            "main.threading.Thread"
        ):
            app.start_listening(None)
        main.rumps.notification.assert_called_once()
        titulo = main.rumps.notification.call_args[0][1]
        self.assertIn("Bluetooth", titulo)


class ErroDePermissaoTest(unittest.TestCase):
    def setUp(self):
        main.rumps.alert.reset_mock()
        main.rumps.notification.reset_mock()

    def test_permissao_negada_explica_o_caminho_dos_ajustes(self):
        # Antes isso caía no mesmo "erro no áudio" das falhas de stream,
        # mandando investigar o microfone quando o que faltava era um
        # clique em Ajustes do Sistema.
        app = _build_app(load_model=True)
        app.listening = True
        with patch.object(
            app,
            "_listen_loop",
            side_effect=main.actions.AutomationDenied("not allowed assistive access"),
        ):
            app._listen_loop_safe()
        self.assertFalse(app.listening)
        self.assertEqual(app.title, main.STATE_GLYPHS["error"])
        mensagem = main.rumps.alert.call_args[0][0]
        self.assertIn("Accessibility", mensagem)

    def test_erro_de_audio_continua_sendo_erro_de_audio(self):
        app = _build_app(load_model=True)
        app.listening = True
        with patch.object(app, "_listen_loop", side_effect=OSError("device gone")):
            app._listen_loop_safe()
        self.assertFalse(app.listening)
        self.assertEqual(app.title, main.STATE_GLYPHS["error"])
        main.rumps.alert.assert_not_called()
        self.assertIn("Audio error", main.rumps.notification.call_args[0][2])


class MenuDeMicrofoneTest(unittest.TestCase):
    def test_primeira_construcao_nao_quebra_no_clear(self):
        # Regressão de um bug real, encontrado rodando num Mac de
        # verdade: main._rebuild_mic_menu() chamava mic_menu.clear()
        # incondicionalmente, e o rumps só cria o NSMenu interno do
        # submenu no primeiro .add() — chamar .clear() ANTES disso
        # (exatamente o caso da chamada vinda do __init__, a
        # primeiríssima) levantava AttributeError e derrubava o app
        # antes do ícone existir. _build_app() já dispara essa
        # primeira chamada sozinho; não pode levantar nada.
        app = _build_app(devices=[(0, "DJI Mic")])
        titulos = [item.title for item in app.mic_menu.items]
        self.assertIn("Detect automatically", titulos)
        self.assertIn("DJI Mic", titulos)

    def test_reconstrucoes_seguidas_tambem_nao_quebram(self):
        # A partir da segunda vez, .clear() TEM que ser chamado de
        # verdade (senão dispositivo desconectado continuaria
        # aparecendo no menu) — cobre que o guard não desliga o clear
        # pra sempre, só pula a primeiríssima chamada.
        app = _build_app(devices=[(0, "DJI Mic")])
        with patch("main.list_input_devices", return_value=[(0, "DJI Mic")]):
            app._rebuild_mic_menu()
            app._rebuild_mic_menu()
            app._rebuild_mic_menu()
        titulos = [item.title for item in app.mic_menu.items]
        self.assertEqual(titulos, ["Detect automatically", "DJI Mic"])

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
        self.assertFalse(estados["Detect automatically"])
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

    def test_falha_ao_enumerar_audio_nao_derruba_o_menu(self):
        # Enumerar áudio pode falhar (PortAudio ausente, permissão não
        # concedida). No __init__, uma exceção aqui matava o app antes
        # do ícone existir.
        app = _build_app()
        with patch("main.list_input_devices", side_effect=OSError("PortAudio")):
            app._rebuild_mic_menu()
        titulos = [item.title for item in app.mic_menu.items]
        self.assertEqual(titulos, ["Detect automatically"])


class ConfiguracaoPeloAppTest(unittest.TestCase):
    """
    Instalada pelo .dmg, ela não tem Terminal nem a pasta do projeto —
    `python3 setup_visper.py` é inalcançável. Sem isto, o caminho "sem
    atrito" era o único SEM jeito de configurar o iPhone.
    """

    def setUp(self):
        main.rumps.alert.reset_mock()
        main.rumps.Window.reset_mock()

    def test_salva_o_topico_digitado(self):
        app = _build_app()
        main.rumps.Window.return_value.run.return_value = FakeWindowResponse(
            clicked=1, text="visper-abc123"
        )
        with patch("main.save_settings", return_value=True) as fake_save:
            app.open_settings(None)
        fake_save.assert_called_once_with({"NTFY_TOPIC": "visper-abc123"})

    def test_tolera_colar_a_url_inteira_do_ntfy(self):
        app = _build_app()
        main.rumps.Window.return_value.run.return_value = FakeWindowResponse(
            clicked=1, text="https://ntfy.sh/visper-abc123/"
        )
        with patch("main.save_settings", return_value=True) as fake_save:
            app.open_settings(None)
        fake_save.assert_called_once_with({"NTFY_TOPIC": "visper-abc123"})

    def test_cancelar_nao_salva(self):
        app = _build_app()
        main.rumps.Window.return_value.run.return_value = FakeWindowResponse(
            clicked=0, text="visper-abc123"
        )
        with patch("main.save_settings") as fake_save:
            app.open_settings(None)
        fake_save.assert_not_called()

    def test_campo_vazio_mantem_o_que_ja_estava(self):
        app = _build_app()
        main.rumps.Window.return_value.run.return_value = FakeWindowResponse(
            clicked=1, text="   "
        )
        with patch("main.save_settings") as fake_save:
            app.open_settings(None)
        fake_save.assert_not_called()


class SairTest(unittest.TestCase):
    def test_sair_para_a_escuta_antes_de_fechar(self):
        # Sem isso, a thread de áudio pode continuar segurando o
        # microfone depois do app sumir da barra — e, com fone
        # Bluetooth, mantendo o áudio do sistema em mono.
        app = _build_app(load_model=True)
        app.listening = True
        with patch.object(main.rumps, "quit_application") as fake_quit:
            app.quit_app(None)
        self.assertFalse(app.listening)
        fake_quit.assert_called_once()


if __name__ == "__main__":
    unittest.main()

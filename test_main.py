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
menu renderizar mesmo, o AppKit aceitar ícone/título mutável de
verdade, e o áudio. O despacho REAL pra thread principal (AppHelper.
callAfter, ver main._set_state()) também só é validável lá — aqui o
dublê de AppHelper executa na hora, sem run loop nenhum por trás.
"""

import os
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
    def __init__(self, name, title=None, icon=None, quit_button=None):
        # main.VisperApp agora comunica estado pelo ÍCONE (círculo
        # colorido, ver main.STATUS_ICONS), não mais pelo título em
        # emoji — mas o dublê guarda os dois, já que rumps.App aceita
        # os dois parâmetros de verdade.
        self.name = name
        self.title = title
        self.icon = icon
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

    if "PyObjCTools" not in sys.modules:
        # AppHelper.callAfter é COMO main.py despacha qualquer coisa
        # que toque AppKit (ícone, título de menu, rumps.alert) pra
        # thread principal — ver main._set_state()/_set_heard() e o
        # comentário no handler de AutomationDenied. Sem runloop de
        # verdade num sandbox Linux, "despachar" aqui só quer dizer
        # "chamar na hora": suficiente pra testar O QUE seria chamado
        # e COM QUE argumento, que é o que os testes verificam — a
        # entrega assíncrona de verdade só é testável num Mac.
        fake_pyobjctools = types.ModuleType("PyObjCTools")
        fake_apphelper = types.ModuleType("PyObjCTools.AppHelper")
        fake_apphelper.callAfter = lambda func, *args, **kwargs: func(*args, **kwargs)
        fake_pyobjctools.AppHelper = fake_apphelper
        sys.modules["PyObjCTools"] = fake_pyobjctools
        sys.modules["PyObjCTools.AppHelper"] = fake_apphelper


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
        self.assertEqual(app._current_state, "loading")
        self.assertEqual(app.icon, main.STATUS_ICONS["loading"])

    def test_modelo_carregado_deixa_o_app_pronto(self):
        app = _build_app(load_model=True)
        self.assertIsNotNone(app.model)
        self.assertIsNone(app.model_error)
        self.assertEqual(app._current_state, "stopped")

    def test_falha_ao_carregar_guarda_o_motivo_e_nao_levanta(self):
        app = _build_app()
        with patch("main.WhisperModel", side_effect=OSError("sem internet")):
            app._load_model()  # não pode propagar: mataria a thread calada
        self.assertIsNone(app.model)
        self.assertIn("sem internet", app.model_error)
        self.assertEqual(app._current_state, "error")

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
        self.assertEqual(app._current_state, "dictating")

    def test_mandar_pinta_de_enviado(self):
        app = _build_app(load_model=True)
        with patch.object(main.actions, "play_sound"):
            app._on_dictation_send()
        self.assertEqual(app._current_state, "sent")
        app._revert_timer.cancel()

    def test_o_azul_de_enviado_volta_sozinho_pra_escutando(self):
        # "Mandou" é um EVENTO, não uma situação: a escuta continua
        # logo depois. Sem o flash o azul ficava até acontecer outra
        # coisa (podiam ser minutos), e nesse tempo todo o ícone
        # respondia ERRADO a única pergunta que ele existe pra
        # responder — "ele está me ouvindo agora?".
        app = _build_app(load_model=True)
        app.listening = True
        app._flash_state("sent", seconds=0)
        app._revert_timer.join(2)
        self.assertEqual(app._current_state, "listening")

    def test_flash_nao_desfaz_um_estado_que_alguem_ja_mudou(self):
        # Entre o flash e o timer dá tempo de a pessoa apertar "Stop
        # listening", começar outro ditado, ou dar erro. Quem mudou
        # depois tem mais razão que um timer velho.
        app = _build_app(load_model=True)
        app.listening = True
        app._flash_state("sent", seconds=0.4)
        app._set_state("error")
        app._revert_timer.join(2)
        self.assertEqual(app._current_state, "error")

    def test_flash_durante_um_ditado_novo_volta_pra_ditando(self):
        # Falar de novo antes do timer terminar é normal (a resposta
        # vem rápido). O ícone tem que voltar pro estado REAL, não pro
        # que era quando o flash começou.
        app = _build_app(load_model=True)
        app.listening = True
        app.session.dictating = True
        app._flash_state("sent", seconds=0)
        app._revert_timer.join(2)
        self.assertEqual(app._current_state, "dictating")

    def test_flash_com_a_escuta_parada_volta_pro_parado(self):
        app = _build_app(load_model=True)
        app.listening = False
        app._flash_state("sent", seconds=0)
        app._revert_timer.join(2)
        self.assertEqual(app._current_state, "stopped")

    def test_cancelar_ditado_nao_pinta_de_enviado(self):
        # Cancelar e mandar são opostos; se pintassem igual, o ícone
        # diria que o texto foi embora quando ele foi justamente
        # jogado fora.
        app = _build_app(load_model=True)
        app.listening = True
        with patch.object(main.actions, "play_sound"):
            app._on_dictation_cancel()
        self.assertEqual(app._current_state, "listening")

    def test_cancelar_toca_o_som_de_cancelar_nao_o_de_mandar(self):
        app = _build_app(load_model=True)
        app.listening = True
        with patch.object(main.actions, "play_sound") as tocou:
            app._on_dictation_cancel()
        tocou.assert_called_once_with(main.config.DICTATION_CANCEL_SOUND)

    def test_a_sessao_recebe_o_callback_de_cancelamento(self):
        # Sem isso o cancelamento funcionaria na lógica e ficaria MUDO
        # na interface — que é o mesmo que não existir, já que o ponto
        # é saber que o texto não foi mandado.
        app = _build_app()
        self.assertEqual(app.session.on_cancel, app._on_dictation_cancel)

    def test_parar_escuta_volta_pro_parado(self):
        app = _build_app(load_model=True)
        app.listening = True
        app._set_state("listening")
        app.stop_listening(None)
        self.assertFalse(app.listening)
        self.assertEqual(app._current_state, "stopped")

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

    def test_fechar_sem_conteudo_pelo_iphone_nao_trava_no_ditando(self):
        # Bug real: um fechamento sem conteúdo (dictation.py's
        # _finalize() quando o buffer está vazio) NUNCA chama on_send —
        # é a única coisa que reverte o ícone além do `elif
        # self.listening`. Uso só-pelo-iPhone (self.listening False o
        # tempo todo — o cenário principal do relay, longe de casa)
        # ficava com o ícone preso em "dictating" pra sempre depois
        # disso, mesmo com o app inteiramente ocioso.
        app = _build_app(load_model=True)
        app.listening = False
        app._set_state("dictating")
        app.session.dictating = False  # a sessão já fechou

        app._on_result("opened claude — listening for dictation; nothing to send — the dictation was empty")

        self.assertEqual(app._current_state, "stopped")

    def test_fechar_sem_conteudo_com_a_escuta_local_ligada_volta_pra_escutando(self):
        app = _build_app(load_model=True)
        app.listening = True
        app._set_state("dictating")
        app.session.dictating = False

        app._on_result("nothing to send — the dictation was empty")

        self.assertEqual(app._current_state, "listening")

    def test_resultado_do_iphone_nao_atropela_o_flash_de_enviado(self):
        # Uma mensagem SEGUINTE que também fecha (ex.: outra vinda do
        # iPhone logo em seguida) não pode apagar o flash azul de
        # "mandou" antes dos ~2,5s — mesma regra que já vale pro mic.
        app = _build_app(load_model=True)
        app.listening = True
        app._set_state("sent")
        app.session.dictating = False

        app._on_result("nothing to send — the dictation was empty")

        self.assertEqual(app._current_state, "sent")


class IconesDeStatusTest(unittest.TestCase):
    """
    STATUS_ICONS são PNGs de VERDADE: a silhueta do mascote do
    briefing (design/menubar_icon_template.svg) nas cores exatas de
    design/layouts_mockup.html — não mais emoji (cujas cores são as do
    fonte da Apple) nem círculo liso (que perdia a identidade). A
    fidelidade do desenho e da cor é conferida em
    test_status_icons.py, contra os bytes do PNG; aqui só o que
    main.py precisa: as 6 chaves e os arquivos existindo.
    """

    def test_todo_estado_tem_icone_e_o_arquivo_existe(self):
        # STATE_GLYPHS tinha 6 chaves fixas; STATUS_ICONS precisa
        # continuar com as MESMAS 6, e cada uma apontando pra um PNG
        # que existe de verdade — se o asset sumir do repo (ex.:
        # alguém apaga status_icons/ sem querer), main.py abriria e
        # morreria tentando carregar um ícone inexistente.
        esperados = {"stopped", "loading", "listening", "dictating", "sent", "error"}
        self.assertEqual(set(main.STATUS_ICONS), esperados)
        for estado, caminho in main.STATUS_ICONS.items():
            with self.subTest(estado=estado):
                self.assertTrue(
                    os.path.isfile(caminho), f"{caminho} não existe"
                )
                self.assertTrue(caminho.endswith(".png"))

    def test_icone_inicial_e_o_de_carregando(self):
        app = _build_app()
        self.assertEqual(app.icon, main.STATUS_ICONS["loading"])

    def test_construtor_usa_nome_fixo_nao_o_glifo_de_estado(self):
        # Regressão de um detalhe sutil: rumps.App usa o parâmetro
        # `name` (não `title`) pra nomear a pasta de Application
        # Support dele (rumps.application_support). A versão em emoji
        # passava o GLIFO DE ESTADO ali (ex.: "⏳") — inofensivo, mas
        # sem sentido, e escondia esse acoplamento. Agora é "vIsper" de
        # verdade.
        app = _build_app()
        self.assertEqual(app.name, "vIsper")


class DespachoParaThreadPrincipalTest(unittest.TestCase):
    """
    _set_state()/_set_heard()/o rumps.alert() de permissão negada são
    chamados de THREADS DE FUNDO (_load_model, _listen_loop_*,
    _on_result vindo do relay) — mexer em AppKit (ícone, título de
    menu, NSAlert) fora da main thread é a violação real que crashou
    o app rodando de verdade: "Must only be used from the main
    thread", bem no meio de _rebuild_mic_menu/popUpStatusBarMenu.

    Estes testes checam que o CAMINHO passa por AppHelper.callAfter —
    não só que o efeito final acontece (isso os testes de
    EstadoNaBarraTest já cobrem, com o dublê de callAfter executando
    na hora). Patcheia main.AppHelper.callAfter direto por um
    MagicMock (em vez do dublê global que executa na hora) pra
    inspecionar OS ARGUMENTOS da chamada.
    """

    def test_set_state_despacha_via_callafter(self):
        app = _build_app()
        with patch.object(main.AppHelper, "callAfter") as fake_call_after:
            app._set_state("listening")
        fake_call_after.assert_called_once_with(
            setattr, app, "icon", main.STATUS_ICONS["listening"]
        )
        # O estado LÓGICO já reflete a troca na hora — só a mutação de
        # AppKit em si que é assíncrona (ver o comentário na função).
        self.assertEqual(app._current_state, "listening")

    def test_set_heard_despacha_via_callafter(self):
        app = _build_app()
        with patch.object(main.AppHelper, "callAfter") as fake_call_after:
            app._set_heard("oi tudo bem")
        fake_call_after.assert_called_once_with(
            setattr, app.heard_item, "title", "Heard: oi tudo bem"
        )

    def test_alerta_de_permissao_negada_despacha_via_callafter(self):
        app = _build_app(load_model=True)
        app.listening = True
        with patch.object(
            app,
            "_listen_loop",
            side_effect=main.actions.AutomationDenied("not allowed assistive access"),
        ), patch.object(main.AppHelper, "callAfter") as fake_call_after:
            app._listen_loop_safe()
        # rumps.alert (não uma lambda/wrapper) precisa ser o primeiro
        # argumento — é o que garante que o alerta realmente aparece,
        # só que despachado, em vez de silenciosamente não chamado.
        self.assertEqual(fake_call_after.call_args[0][0], main.rumps.alert)
        mensagem = fake_call_after.call_args[0][1]
        self.assertIn("Accessibility", mensagem)


class _FakeSegment:
    def __init__(self, text):
        self.text = text


class _FakeInfo:
    def __init__(self, language, probability=0.99):
        self.language = language
        self.language_probability = probability


class IdiomaDeTranscricaoTest(unittest.TestCase):
    """
    config.TRANSCRIPTION_LANGUAGES é a resposta pra "só funciona em
    inglês" / "quero falar português E inglês".

    O ponto que torna isto uma correção de verdade e não só um rótulo:
    o Whisper transcreve NO idioma que ele detectou, então detecção
    errada produz TEXTO errado. Detectar mal num trecho de ~4s é
    conhecidamente comum. Por isso, com vários idiomas permitidos, uma
    detecção fora da lista (ou insegura) faz o trecho ser REFEITO no
    idioma de reserva, em vez de aceitar o texto errado.
    """

    def _model_devolvendo(self, respostas):
        """respostas: lista de (texto, idioma, confiança) por chamada."""
        model = MagicMock()
        model.transcribe.side_effect = [
            ([_FakeSegment(texto)], _FakeInfo(idioma, prob))
            for texto, idioma, prob in respostas
        ]
        return model

    def _um_chunk(self, app):
        stream = MagicMock()
        stream.chunks.return_value = iter([object()])
        with patch.object(app.session, "handle", return_value=None):
            app._listen_loop_whisper(stream)

    # -- um idioma só: força, nem detecta -----------------------------

    def test_um_idioma_forca_e_nao_detecta(self):
        app = _build_app(load_model=True)
        app.listening = True
        app._allowed_languages = ["pt"]
        app._forced_language = "pt"
        app.model = self._model_devolvendo([("oi tudo bem", "pt", 0.99)])

        self._um_chunk(app)

        self.assertEqual(app.model.transcribe.call_count, 1)
        self.assertEqual(app.model.transcribe.call_args.kwargs["language"], "pt")
        self.assertEqual(app._last_heard, "[pt] oi tudo bem")

    # -- vários idiomas: detecta, mas valida --------------------------

    def test_deteccao_dentro_da_lista_e_confiante_e_aceita(self):
        app = _build_app(load_model=True)
        app.listening = True
        app._allowed_languages = ["pt", "en"]
        app._forced_language = None
        app.model = self._model_devolvendo([("oi tudo bem", "pt", 0.95)])

        self._um_chunk(app)

        self.assertEqual(app.model.transcribe.call_count, 1, "não devia refazer")
        self.assertIsNone(app.model.transcribe.call_args.kwargs["language"])
        self.assertEqual(app._last_heard, "[pt] oi tudo bem")
        self.assertEqual(app._last_good_language, "pt")

    def test_deteccao_fora_da_lista_refaz_no_idioma_de_reserva(self):
        # O caso real: ela fala português, o Whisper crava um idioma
        # que ela nem fala, e o TEXTO sai transcrito naquele idioma.
        # Aceitar isso é aceitar letra errada — por isso refaz.
        app = _build_app(load_model=True)
        app.listening = True
        app._allowed_languages = ["pt", "en"]
        app._forced_language = None
        app.model = self._model_devolvendo(
            [("oi tud bem", "cy", 0.99), ("oi tudo bem", "pt", 0.99)]
        )

        self._um_chunk(app)

        self.assertEqual(app.model.transcribe.call_count, 2)
        # Segunda passada força o idioma de reserva.
        self.assertEqual(
            app.model.transcribe.call_args_list[1].kwargs["language"], "pt"
        )
        # O rótulo mostra os dois: o que detectou e o que usou.
        self.assertEqual(app._last_heard, "[cy→pt] oi tudo bem")

    def test_deteccao_insegura_refaz_mesmo_estando_na_lista(self):
        app = _build_app(load_model=True)
        app.listening = True
        app._allowed_languages = ["pt", "en"]
        app._forced_language = None
        baixa = main.config.LANGUAGE_CONFIDENCE_THRESHOLD - 0.1
        app.model = self._model_devolvendo(
            [("oi", "en", baixa), ("oi tudo bem", "pt", 0.99)]
        )

        self._um_chunk(app)

        self.assertEqual(app.model.transcribe.call_count, 2)
        self.assertEqual(app._last_heard, "[en→pt] oi tudo bem")

    def test_reserva_e_o_ultimo_idioma_que_deu_certo(self):
        # Pessoa não troca de idioma a cada 4s: "o que estava valendo
        # agora há pouco" acerta mais que o primeiro da lista.
        app = _build_app(load_model=True)
        app.listening = True
        app._allowed_languages = ["pt", "en"]
        app._forced_language = None
        app._last_good_language = "en"  # ela estava falando inglês
        app.model = self._model_devolvendo(
            [("bla", "cy", 0.99), ("how are you", "en", 0.99)]
        )

        self._um_chunk(app)

        self.assertEqual(
            app.model.transcribe.call_args_list[1].kwargs["language"], "en"
        )
        self.assertEqual(app._last_heard, "[cy→en] how are you")

    # -- lista vazia: sem restrição -----------------------------------

    def test_lista_vazia_aceita_qualquer_idioma_sem_refazer(self):
        app = _build_app(load_model=True)
        app.listening = True
        app._allowed_languages = []
        app._forced_language = None
        app.model = self._model_devolvendo([("hola", "es", 0.4)])

        self._um_chunk(app)

        self.assertEqual(app.model.transcribe.call_count, 1)
        self.assertEqual(app._last_heard, "[es] hola")

    # -- parâmetros que valem pra toda passada ------------------------

    def test_hotwords_e_vad_vao_em_todas_as_passadas(self):
        app = _build_app(load_model=True)
        app.listening = True
        app._allowed_languages = ["pt", "en"]
        app._forced_language = None
        app.model = self._model_devolvendo(
            [("bla", "cy", 0.99), ("oi", "pt", 0.99)]
        )

        self._um_chunk(app)

        for chamada in app.model.transcribe.call_args_list:
            self.assertEqual(chamada.kwargs["hotwords"], app._hotwords)
            self.assertTrue(chamada.kwargs["vad_filter"])


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
        self.assertEqual(app._current_state, "listening")

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
        self.assertEqual(app._current_state, "error")
        mensagem = main.rumps.alert.call_args[0][0]
        self.assertIn("Accessibility", mensagem)

    def test_permissao_negada_abre_o_painel_de_ajustes_sozinho(self):
        # Descrever o caminho por escrito não basta: são quatro níveis
        # de menu, e quem está tentando usar de mãos ocupadas é
        # justamente quem menos consegue navegar isso.
        app = _build_app(load_model=True)
        app.listening = True
        with patch("main.subprocess.run") as run:
            with patch.object(
                app,
                "_listen_loop",
                side_effect=main.actions.AutomationDenied("not allowed"),
            ):
                app._listen_loop_safe()
        argumentos = run.call_args[0][0]
        self.assertEqual(argumentos[0], "open")
        self.assertIn("Privacy_Accessibility", argumentos[1])

    def test_painel_que_nao_abre_nao_vira_um_segundo_erro(self):
        # É conveniência em cima de um alerta que já explica o caminho —
        # falhar aqui não pode atrapalhar o aviso de verdade.
        app = _build_app(load_model=True)
        app.listening = True
        with patch("main.subprocess.run", side_effect=OSError("no open")):
            with patch.object(
                app,
                "_listen_loop",
                side_effect=main.actions.AutomationDenied("not allowed"),
            ):
                app._listen_loop_safe()
        self.assertIn("Accessibility", main.rumps.alert.call_args[0][0])

    def test_erro_de_audio_continua_sendo_erro_de_audio(self):
        app = _build_app(load_model=True)
        app.listening = True
        with patch.object(app, "_listen_loop", side_effect=OSError("device gone")):
            app._listen_loop_safe()
        self.assertFalse(app.listening)
        self.assertEqual(app._current_state, "error")
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

    def test_gera_um_topico_aleatorio_sem_precisar_do_script(self):
        # Sem isto, TODO caminho documentado pra conseguir um tópico
        # passava pelo setup_visper.py — que quem instalou pelo .dmg não
        # tem. A única saída sobrando era inventar um à mão, e o tópico
        # é justamente a senha do canal.
        app = _build_app()
        main.rumps.Window.return_value.run.return_value = FakeWindowResponse(
            clicked=1, text="new"
        )
        with patch("main.copiar_para_area_de_transferencia", return_value=True):
            with patch("main.save_settings", return_value=True) as fake_save:
                app.open_settings(None)
        salvo = fake_save.call_args[0][0]["NTFY_TOPIC"]
        self.assertTrue(salvo.startswith("visper-"))
        self.assertGreater(len(salvo), 24)

    def test_dois_topicos_gerados_nunca_sao_iguais(self):
        gerados = set()
        for _ in range(5):
            app = _build_app()
            main.rumps.Window.return_value.run.return_value = FakeWindowResponse(
                clicked=1, text="new"
            )
            with patch("main.copiar_para_area_de_transferencia", return_value=True):
                with patch("main.save_settings", return_value=True) as fake_save:
                    app.open_settings(None)
            gerados.add(fake_save.call_args[0][0]["NTFY_TOPIC"])
        self.assertEqual(len(gerados), 5)

    def test_o_topico_gerado_aparece_pra_pessoa_copiar_no_telefone(self):
        # Ele precisa ser digitado no iPhone; se só fosse salvo em
        # silêncio, não haveria de onde tirar.
        app = _build_app()
        main.rumps.Window.return_value.run.return_value = FakeWindowResponse(
            clicked=1, text="new"
        )
        with patch("main.copiar_para_area_de_transferencia", return_value=True):
            with patch("main.save_settings", return_value=True) as fake_save:
                app.open_settings(None)
        salvo = fake_save.call_args[0][0]["NTFY_TOPIC"]
        texto = " ".join(str(a) for a in main.rumps.alert.call_args[0])
        self.assertIn(salvo, texto)

    def test_colar_so_o_endereco_sem_topico_nao_desliga_o_relay(self):
        # Depois de tirar o prefixo sobrava "" — e "" GRAVADO desliga o
        # relay, enquanto o alerta dizia que tinha salvado. Desligar tem
        # que ser escolha, não efeito colateral de colar errado.
        app = _build_app()
        main.rumps.alert.reset_mock()
        main.rumps.Window.return_value.run.return_value = FakeWindowResponse(
            clicked=1, text="https://ntfy.sh/"
        )
        with patch("main.save_settings") as fake_save:
            app.open_settings(None)
        fake_save.assert_not_called()
        self.assertTrue(main.rumps.alert.called)

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


class ConfigurarPeloMenuTest(unittest.TestCase):
    """Wake word e idiomas ajustáveis SEM Terminal.

    Quem instalou pelo .dmg não tem o repositório nem o
    setup_visper.py na máquina — mandar essa pessoa "editar o
    config.py" é exatamente o atrito que o .dmg existe pra tirar.
    """

    def setUp(self):
        main.rumps.alert.reset_mock()
        main.rumps.Window.reset_mock()
        self._idiomas = list(main.config.TRANSCRIPTION_LANGUAGES)

    def tearDown(self):
        main.config.TRANSCRIPTION_LANGUAGES = self._idiomas

    def _responder(self, texto, clicked=1):
        main.rumps.Window.return_value.run.return_value = FakeWindowResponse(
            clicked=clicked, text=texto
        )

    def test_os_ajustes_aparecem_no_menu(self):
        app = _build_app()
        titulos = [item for item in app.menu if isinstance(item, str)]
        for esperado in ("Wake word…", "Spoken languages…", "iPhone connection…"):
            self.assertIn(esperado, titulos)

    def test_salva_a_wake_word_nova(self):
        app = _build_app()
        self._responder("Vésper")
        with patch("main.save_settings", return_value=True) as fake_save:
            app.open_wake_word(None)
        fake_save.assert_called_once_with({"WAKE_WORD": "Vésper"})

    def test_wake_word_igual_a_atual_nao_grava_nada(self):
        app = _build_app()
        self._responder(main.config.WAKE_WORD)
        with patch("main.save_settings") as fake_save:
            app.open_wake_word(None)
        fake_save.assert_not_called()

    def test_cancelar_a_janela_da_wake_word_nao_grava(self):
        app = _build_app()
        self._responder("Vésper", clicked=0)
        with patch("main.save_settings") as fake_save:
            app.open_wake_word(None)
        fake_save.assert_not_called()

    def test_salva_lista_de_idiomas(self):
        app = _build_app()
        self._responder("pt, en, es")
        with patch("main.save_settings", return_value=True) as fake_save:
            app.open_languages(None)
        fake_save.assert_called_once_with(
            {"TRANSCRIPTION_LANGUAGES": ["pt", "en", "es"]}
        )

    def test_auto_vira_lista_vazia(self):
        app = _build_app()
        self._responder("auto")
        with patch("main.save_settings", return_value=True) as fake_save:
            app.open_languages(None)
        fake_save.assert_called_once_with({"TRANSCRIPTION_LANGUAGES": []})

    def test_mudar_idioma_vale_na_hora_sem_reiniciar(self):
        # O ajuste que a pessoa mais vai querer tentar de novo (é ele
        # que conserta "só funciona em inglês") não pode exigir fechar
        # e reabrir o app a cada tentativa.
        app = _build_app()
        self._responder("pt")
        with patch("main.save_settings", return_value=True):
            app.open_languages(None)
        self.assertEqual(app._allowed_languages, ["pt"])
        self.assertEqual(app._forced_language, "pt")

    def test_voltar_pra_varios_idiomas_desliga_o_forcado(self):
        app = _build_app()
        self._responder("pt")
        with patch("main.save_settings", return_value=True):
            app.open_languages(None)
        self._responder("pt, en")
        with patch("main.save_settings", return_value=True):
            app.open_languages(None)
        self.assertIsNone(app._forced_language)
        self.assertEqual(app._allowed_languages, ["pt", "en"])

    def test_idioma_de_reserva_e_esquecido_ao_trocar_a_lista(self):
        # Guardado de uma lista antiga, ele pode nem estar na nova —
        # continuaria forçando um idioma que ela acabou de tirar.
        app = _build_app()
        app._last_good_language = "en"
        self._responder("pt, es")
        with patch("main.save_settings", return_value=True):
            app.open_languages(None)
        self.assertIsNone(app._last_good_language)

    def test_codigo_de_idioma_invalido_e_recusado_antes_de_salvar(self):
        # "português", "pt-BR" e "eng" são palpites naturais de quem
        # fala português, e todos os três quebram o Whisper — a exceção
        # só aparece lá na frente, DENTRO do laço de transcrição, e
        # derruba a escuta inteira minutos depois do ajuste. Recusar na
        # hora é o que liga o erro à causa.
        for ruim in ("português", "pt-BR", "eng", "portuguese"):
            with self.subTest(codigo=ruim):
                app = _build_app()
                main.rumps.alert.reset_mock()
                self._responder(ruim)
                with patch("main.save_settings") as fake_save:
                    app.open_languages(None)
                fake_save.assert_not_called()
                texto = " ".join(str(a) for a in main.rumps.alert.call_args[0])
                self.assertIn(ruim, texto)

    def test_um_codigo_ruim_no_meio_invalida_a_lista_inteira(self):
        app = _build_app()
        self._responder("pt, xx, en")
        with patch("main.save_settings") as fake_save:
            app.open_languages(None)
        fake_save.assert_not_called()

    def test_idioma_invalido_nao_mexe_no_que_ja_estava_valendo(self):
        app = _build_app()
        self._responder("pt")
        with patch("main.save_settings", return_value=True):
            app.open_languages(None)
        self._responder("pt-BR")
        with patch("main.save_settings"):
            app.open_languages(None)
        self.assertEqual(app._allowed_languages, ["pt"])
        self.assertEqual(app._forced_language, "pt")

    def test_falha_ao_gravar_avisa_em_vez_de_fingir_que_salvou(self):
        app = _build_app()
        self._responder("Vésper")
        with patch("main.save_settings", return_value=False):
            app.open_wake_word(None)
        self.assertTrue(main.rumps.alert.called)
        texto = " ".join(str(a) for a in main.rumps.alert.call_args[0])
        self.assertIn("Could not write", texto)


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


class HistoricoDeAtividadeTest(unittest.TestCase):
    """
    "Recent activity…" existe pro teste de verdade no Mac: quando um
    comando não funciona, a pergunta é sempre "o que ele entendeu?" —
    e o "Heard:" do menu só guarda o ÚLTIMO trecho, cortado em 45
    caracteres, sobrescrito pelo próximo em ~4 segundos. Quando ela
    abre o menu pra olhar, a prova já foi embora.
    """

    def test_o_que_foi_ouvido_entra_no_historico(self):
        app = _build_app(load_model=True)
        app._set_heard("[pt] vIsper claude qual é a previsão")
        self.assertTrue(
            any("vIsper claude qual é a previsão" in l for l in app._history)
        )

    def test_o_historico_guarda_inteiro_o_que_o_menu_corta(self):
        # O "Heard:" corta em 45 caracteres porque item de menu
        # comprido fica horrível — mas é justamente o fim da frase que
        # costuma trazer o gatilho de fechamento. Cortar ali no
        # histórico repetiria a limitação que ele existe pra resolver.
        longa = "vIsper claude " + ("palavra " * 20) + "over"
        app = _build_app(load_model=True)
        app._set_heard(longa)
        self.assertTrue(any(longa in l for l in app._history))
        self.assertIn("…", app.heard_item.title)

    def test_linha_comprida_e_encurtada_pelo_meio_nao_pelo_fim(self):
        # As duas pontas são o diagnóstico: a wake word abre a frase e o
        # gatilho de fechamento a fecha. Encurtar pelo fim jogaria fora
        # metade da resposta — e é justamente a metade que explica por
        # que o ditado não foi mandado.
        longa = "vIsper claude " + ("palavra " * 40) + "over"
        curta = main._elide(f"09:41:58  heard  {longa}")
        self.assertLessEqual(len(curta), main.HISTORY_LINE_MAX)
        self.assertIn("vIsper claude", curta)
        self.assertTrue(curta.endswith("over"))
        self.assertIn("...", curta)

    def test_linha_curta_passa_intacta(self):
        linha = "09:41:58  heard  vIsper claude"
        self.assertEqual(main._elide(linha), linha)

    def test_encurtar_respeita_o_limite_por_menor_que_ele_seja(self):
        # Um "fim" fixo maior que o limite deixaria o início NEGATIVO, e
        # aí a fatia cortaria pelo fim em vez de truncar — devolvendo em
        # silêncio uma linha errada e MAIS comprida que a pedida.
        longa = "x" * 500
        for limite in (5, 10, 30, 43, 110, 400):
            with self.subTest(limite=limite):
                self.assertLessEqual(len(main._elide(longa, limite)), limite)

    def test_a_decisao_entra_junto_com_o_que_foi_ouvido(self):
        # As duas metades importam separadas: a falha mais comum é elas
        # não combinarem (ouviu certo, decidiu errado — ou nem ouviu).
        app = _build_app(load_model=True)
        app.listening = True
        app._set_heard("[pt] vIsper claude")
        app._on_result("opened claude — listening for dictation")
        texto = "\n".join(app._history)
        self.assertIn("heard", texto)
        self.assertIn("→", texto)
        self.assertIn("opened claude", texto)

    def test_silencio_nao_polui_o_historico(self):
        # Trecho sem fala transcreve vazio o tempo todo. Se cada um
        # virasse linha, as 40 linhas seriam consumidas por silêncio e
        # o comando que falhou já teria saído da janela.
        app = _build_app(load_model=True)
        app._set_heard("")
        app._on_result(None)
        self.assertEqual(list(app._history), [])

    def test_o_historico_nao_cresce_pra_sempre(self):
        # O app escuta o tempo todo: sem teto, uma sessão longa vira
        # vazamento de memória — e o alerta ficaria alto demais pra ler.
        app = _build_app(load_model=True)
        total = main.HISTORY_MAX + 25
        for i in range(total):
            app._set_heard(f"trecho {i}")
        self.assertEqual(len(app._history), main.HISTORY_MAX)
        # O que sobra é o RECENTE, não o começo: a pergunta é sempre
        # sobre o que acabou de acontecer.
        self.assertTrue(any(l.endswith(f"trecho {total - 1}") for l in app._history))
        self.assertFalse(any(l.endswith("trecho 0") for l in app._history))

    def test_o_item_existe_no_menu(self):
        # O handler pode estar perfeito e o item não aparecer: o rumps
        # liga @rumps.clicked ao item pelo TÍTULO, então uma diferença
        # de um caractere ("..." em vez de "…") deixa o menu sem o item
        # e sem erro nenhum.
        app = _build_app()
        titulos = [item for item in app.menu if isinstance(item, str)]
        self.assertIn("Recent activity…", titulos)

    def test_o_menu_mostra_as_linhas_guardadas(self):
        app = _build_app(load_model=True)
        app._set_heard("[pt] vIsper claude")
        main.rumps.alert.reset_mock()
        app.open_activity(None)
        main.rumps.alert.assert_called_once()
        # O texto transcrito vai como `message` (2º argumento), não
        # como `title`: é `message` que o rumps escapa contra "%".
        self.assertIn("vIsper claude", main.rumps.alert.call_args[0][1])

    def test_historico_vazio_explica_em_vez_de_abrir_janela_em_branco(self):
        app = _build_app(load_model=True)
        main.rumps.alert.reset_mock()
        app.open_activity(None)
        main.rumps.alert.assert_called_once()
        self.assertIn("Nothing yet", main.rumps.alert.call_args[0][1])

    def test_mensagem_do_iphone_entra_no_historico_mesmo_sem_bater_com_nada(self):
        # O bug que isto fecha: se a wake word do Mac mudar sem
        # atualizar o link salvo no iPhone, RelayListener nunca chama
        # on_result (handle_complete devolve None) — sem
        # _log_relay_received, essa falha não deixava rastro NENHUM em
        # "Recent activity", justo a ferramenta feita pra diagnosticar
        # "por que não funcionou".
        app = _build_app(load_model=True)
        app._log_relay_received("iris claude oi over")
        self.assertTrue(any("iris claude oi over" in l for l in app._history))
        self.assertTrue(any("phone" in l for l in app._history))


class RelayDoIphoneTest(unittest.TestCase):
    def test_relay_e_construido_com_o_log_de_atividade(self):
        # Sem isto, nenhuma mensagem do iPhone aparecia em "Recent
        # activity" antes mesmo de saber se ela bateu com algum
        # gatilho — ver _log_relay_received().
        with patch.object(main.config, "NTFY_TOPIC", "topico-de-teste-bem-aleatorio"):
            app = _build_app(load_model=True)
        self.assertIsNotNone(app.relay)
        self.assertEqual(app.relay.on_message, app._log_relay_received)

    def test_sem_topico_configurado_o_relay_continua_desligado(self):
        with patch.object(main.config, "NTFY_TOPIC", ""):
            app = _build_app(load_model=True)
        self.assertIsNone(app.relay)


if __name__ == "__main__":
    unittest.main()

"""
vIsper — lançador ativado por voz + interface completa de ditado.

Dois caminhos de escuta, escolhidos automaticamente:
  - Sem PORCUPINE_ACCESS_KEY/PORCUPINE_KEYWORD_PATH configurados:
    transcreve tudo continuamente com Whisper e procura a wake word
    no texto (_listen_loop_whisper). Simples, já validado na lógica,
    mas gasta mais CPU e um falso positivo no meio de uma frase corta
    o ditado cedo demais.
  - Com as duas chaves configuradas: usa o Porcupine pra detectar o
    SOM da wake word em vez de procurar ela numa transcrição
    (_listen_loop_porcupine, ver porcupine_session.py). Bem menos
    falso positivo/negativo — mas essa junção com hardware real ainda
    não foi testada numa máquina de verdade (ver aviso no método).

Em ambos os casos, o texto processado vira: abrir uma IA, acumular
como ditado, ou mandar ver (colar + Enter) — via DictationSession,
compartilhada também com o relay do iPhone (relay_listener.py).

Microfone: DJI Mic (USB) e fones Bluetooth (ex.: Sony WH-1000XM5) são
reconhecidos automaticamente via config.PREFERRED_INPUT_DEVICES; se
nenhum estiver por perto, cai no microfone padrão do sistema (ver
audio_input.default_input_device) em vez de recusar a escutar. Dá pra
escolher manualmente no submenu "Microphone" também.

É um app de menu bar (rumps), então fica discreto. O ÍCONE em si é o
principal indicador de estado — ver ESTADOS logo abaixo.

Texto de interface em INGLÊS de propósito (decisão registrada no
CLAUDE.md); comentários e documentação continuam em português.
"""

import re
import threading
import rumps
from faster_whisper import WhisperModel

from audio_input import (
    AudioStream,
    list_input_devices,
    label_devices,
    guess_preferred_device,
    default_input_device,
    classify_device,
    resolve_device_by_name,
    load_saved_device_name,
    save_device_choice,
)
from command_router import CommandRouter
from dictation import DictationSession
from relay_listener import RelayListener
from user_settings import save_settings, settings_path
from wake_word_porcupine import PorcupineWakeWordDetector
from porcupine_session import PorcupineSession
import actions
import config


MODEL_SIZE = "base"  # tiny/base/small — maior = mais preciso, mais lento
# language=None deixa o Whisper detectar o idioma a cada trecho, pra
# funcionar em português, inglês, ou qualquer outro que você fale.
LANGUAGE = None

# ---------------------------------------------------------------------
# ESTADOS — o que aparece na barra de menu.
#
# Antes o título era fixo ("vIsper") e o único retorno era notificação,
# que some sozinha em segundos. Não dava pra responder a pergunta mais
# básica de todas — "ele está me ouvindo agora?" — sem falar uma frase
# de teste e torcer.
#
# As cores são as MESMAS da paleta semântica de design/layouts_mockup.html
# (cinza=ocioso, verde=escutando, âmbar=ocupado, coral=ditando,
# azul=mandou, terracota=erro). Círculo colorido em vez de imagem
# template porque a bolinha lê bem no tamanho da barra de menu e
# funciona igual em modo claro e escuro, sem precisar de dois assets
# nem de arquivo externo que o py2app teria que empacotar.
# ---------------------------------------------------------------------
STATE_GLYPHS = {
    "stopped": "🎙",    # parado — mas vivo, e claramente o vIsper
    "loading": "⏳",     # carregando o modelo de transcrição
    "listening": "🟢",  # escutando, esperando a wake word
    "dictating": "🔴",  # ouviu a wake word, acumulando o ditado
    "sent": "🔵",       # acabou de colar e mandar
    "error": "🟠",      # algo falhou — o menu explica o quê
}


def notify(titulo, subtitulo, mensagem):
    """
    Notificação do macOS, à prova de falha.

    `rumps.notification()` exige que o processo tenha um bundle com
    identificador — rodando por `python3 main.py` (que é exatamente
    como ela vai testar da primeira vez) ele levanta RuntimeError. Como
    isto é chamado de dentro do loop de ditado e do relay, uma exceção
    aqui derrubava a thread de escuta inteira: o app parava de
    funcionar por causa do MECANISMO DE AVISO, não do que ele avisa.

    Falhou? Vai pro stdout (visível se estiver rodando por Terminal, e
    capturado no visper.out.log quando roda pelo LaunchAgent) e a vida
    segue. O estado real continua visível no ícone da barra de menu,
    que não depende de bundle nenhum.
    """
    try:
        rumps.notification(titulo, subtitulo, mensagem)
    except Exception:
        print(f"[vIsper] {subtitulo}: {mensagem}", flush=True)


class VisperApp(rumps.App):
    def __init__(self):
        super().__init__(STATE_GLYPHS["loading"], icon=None, quit_button=None)
        self.router = CommandRouter(actions.AI_ACTIONS)
        self.session = DictationSession(
            router=self.router,
            paste_action=actions.paste_text,
            send_action=actions.handle_done,
            on_open=self._on_dictation_open,
            on_send=self._on_dictation_send,
        )

        # O modelo do Whisper é carregado numa THREAD, não aqui.
        #
        # Na primeira execução ele BAIXA ~150 MB. Fazendo isso dentro do
        # __init__, o app ficava minutos sem existir — sem ícone, sem
        # janela, sem nada — e quem estivesse esperando concluiria que
        # não abriu. Pior: qualquer falha (sem internet, download
        # cortado, disco cheio) levantava exceção ANTES do ícone existir,
        # então o app morria sem deixar rastro em lugar nenhum. Num .app
        # empacotado não há Terminal pra ver o traceback.
        #
        # Agora o ícone aparece na hora, mostrando ⏳, e vira 🎙 quando o
        # modelo terminar de carregar.
        self.model = None
        self.model_error = None
        self.listening = False

        # Dispositivo de entrada: começa em modo AUTOMÁTICO (device_index
        # None = "detecta de novo, do zero, na próxima vez que precisar" —
        # ver _resolve_device()). Vira manual assim que a pessoa escolhe
        # algo no submenu "Microphone"; volta a automático se ela clicar
        # em "Detect automatically" lá dentro. Cada escolha manual é
        # lembrada entre execuções (audio_input.DEVICE_STATE_PATH) — se
        # existir uma salva, já começa em modo manual com ela; o ÍNDICE
        # só é resolvido de verdade quando precisar (_resolve_device),
        # nunca guardado entre execuções (não é estável, ver
        # resolve_device_by_name()).
        self.device_index = None
        self.device_name = load_saved_device_name()
        self.device_manual = self.device_name is not None
        # Reclassifica a escolha salva pelo NOME: só `_make_pick_device`
        # sabia dizer se o dispositivo é Bluetooth, e isso não sobrevive
        # a fechar o app (só o nome é persistido). Sem isso, reabrir o
        # vIsper com o fone já escolhido deixava device_is_bluetooth em
        # False pra sempre e o aviso de qualidade de áudio nunca mais
        # aparecia — justo no caso em que ele é mais útil (fone
        # escolhido de propósito, sessão após sessão).
        self.device_is_bluetooth = (
            classify_device(self.device_name) if self.device_name else False
        )

        # Handle da thread de escuta — ver o guard em start_listening().
        self._listen_thread = None

        # Última coisa que o Whisper entendeu. Fica visível no menu
        # porque a falha mais confusa deste app é a wake word ser
        # transcrita errada: sem isso, "ele não me ouve" e "ele me ouviu
        # mas escreveu 'visper' com v minúsculo" são indistinguíveis, e
        # a segunda é a mais provável (a wake word padrão é uma palavra
        # inventada — ver "Limite atual do reconhecimento" no README).
        self._last_heard = ""

        self.mic_menu = rumps.MenuItem("Microphone")
        self.heard_item = rumps.MenuItem("Heard: —", callback=None)
        self.menu = [
            self.heard_item,
            None,
            "Start listening",
            "Stop listening",
            None,
            self.mic_menu,
            "Settings…",
            None,
            "Quit vIsper",
        ]
        self._rebuild_mic_menu()

        threading.Thread(target=self._load_model, daemon=True).start()

        # Relay do iPhone via ntfy — só liga se um tópico de verdade
        # estiver configurado (o padrão é ""). Roda numa thread própria,
        # independente da escuta do mic local: os dois alimentam o mesmo
        # self.session, então "abrir pelo Mac" e "abrir pelo iPhone"
        # nunca ficam em estados diferentes.
        self.relay = None
        if config.NTFY_TOPIC:
            self.relay = RelayListener(self.session, topic=config.NTFY_TOPIC)
            threading.Thread(target=self._relay_loop, daemon=True).start()

        # Wake word acústica (opcional) — ver porcupine_session.py.
        # Só ativa se as duas chaves estiverem configuradas; senão o
        # loop de mic local continua no modo Whisper contínuo de hoje.
        # Envolvido em try/except porque uma AccessKey inválida faz o
        # pvporcupine levantar na hora de criar o motor — e isso não
        # pode impedir o app de abrir, já que o modo Whisper funciona
        # perfeitamente sem ele.
        self.porcupine_detector = None
        if config.PORCUPINE_ACCESS_KEY and config.PORCUPINE_KEYWORD_PATH:
            try:
                self.porcupine_detector = PorcupineWakeWordDetector(
                    access_key=config.PORCUPINE_ACCESS_KEY,
                    keyword_path=config.PORCUPINE_KEYWORD_PATH,
                )
            except Exception as exc:
                notify(
                    "vIsper",
                    "Porcupine unavailable",
                    f"Falling back to continuous Whisper. ({exc})",
                )

    # ------------------------------------------------------------------
    # Estado visível na barra de menu
    # ------------------------------------------------------------------

    def _set_state(self, state):
        """Troca o glifo da barra de menu. Ver STATE_GLYPHS."""
        self.title = STATE_GLYPHS.get(state, STATE_GLYPHS["stopped"])

    def _set_heard(self, texto):
        """Mostra no menu o que o Whisper entendeu por último."""
        self._last_heard = texto or ""
        curto = self._last_heard[:45] + ("…" if len(self._last_heard) > 45 else "")
        self.heard_item.title = f"Heard: {curto}" if curto else "Heard: —"

    def _on_dictation_open(self):
        self._set_state("dictating")
        self._play_dictation_sound(config.DICTATION_OPEN_SOUND)

    def _on_dictation_send(self):
        self._set_state("sent")
        self._play_dictation_sound(config.DICTATION_SEND_SOUND)

    # ------------------------------------------------------------------
    # Carregamento do modelo (em thread — ver __init__)
    # ------------------------------------------------------------------

    def _load_model(self):
        try:
            self.model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
            self._set_state("stopped")
        except Exception as exc:
            # Guarda a mensagem em vez de só notificar: a notificação
            # some em segundos e ela pode nem estar olhando na hora.
            # Assim "Start listening" consegue repetir o motivo exato
            # quando ela finalmente tentar usar.
            self.model_error = str(exc)
            self._set_state("error")
            self._set_heard("could not load the speech model")
            notify(
                "vIsper",
                "Speech model failed to load",
                f"{exc} — check your internet connection and reopen vIsper.",
            )

    # ------------------------------------------------------------------
    # Seleção de microfone — automática (DJI > fone Bluetooth > padrão
    # do sistema, ver config.PREFERRED_INPUT_DEVICES) ou manual.
    #
    # NUNCA TESTADO num Mac de verdade, como o resto deste arquivo: a
    # API de submenu dinâmico do rumps usada abaixo (MenuItem.clear()/
    # .add(), estado de checkmark via .state, título mutável via
    # .title) foi conferida linha a linha contra o SOURCE real do
    # pacote (rumps==0.4.0, baixado da PyPI — não só documentação nem
    # de memória), mas isso não substitui ver o AppKit/NSMenu de
    # verdade renderizar o menu.
    # ------------------------------------------------------------------

    def _rebuild_mic_menu(self):
        """Repopula o submenu a partir dos dispositivos ATUALMENTE
        conectados — chamado no __init__ e de novo toda vez que algo
        pode ter mudado (escolha manual, voltou pro automático, ou
        logo antes de tentar escutar), pra refletir fone Bluetooth
        ligado/desligado depois que o app já abriu."""
        self.mic_menu.clear()

        auto_item = rumps.MenuItem("Detect automatically", callback=self._pick_auto)
        auto_item.state = not self.device_manual
        self.mic_menu.add(auto_item)

        # label_devices() desambigua o RÓTULO exibido quando dois
        # dispositivos têm o MESMO nome — sem isso, rumps (que indexa
        # o submenu pelo título) faria o segundo simplesmente sumir do
        # menu. Ver docstring de audio_input.label_devices() pro
        # raciocínio completo (inclui a limitação aceita: seleção
        # continua por nome puro, não pelo rótulo desambiguado).
        try:
            dispositivos = label_devices(list_input_devices())
        except Exception:
            # Enumerar áudio pode falhar (PortAudio ausente, permissão
            # ainda não concedida). Isso não pode impedir o menu de
            # abrir — sem esse guard, um erro aqui no __init__ mataria o
            # app antes do ícone existir.
            dispositivos = []

        for index, name, label in dispositivos:
            item = rumps.MenuItem(label, callback=self._make_pick_device(index, name))
            # Compara por NOME, não índice: logo depois de carregar uma
            # escolha salva (__init__), device_index ainda é None (só é
            # resolvido de verdade na primeira vez que precisar) — comparar
            # por índice deixaria o checkmark faltando até o primeiro
            # "Start listening". Por nome funciona desde o primeiro rebuild.
            item.state = self.device_manual and name == self.device_name
            self.mic_menu.add(item)

        if self.device_name:
            self.mic_menu.title = f"Microphone: {self.device_name}"
        else:
            self.mic_menu.title = "Microphone"

    def _make_pick_device(self, index, name):
        def _pick(_sender):
            self.device_index = index
            self.device_name = name
            self.device_is_bluetooth = classify_device(name)
            self.device_manual = True
            save_device_choice(name)  # lembra pra próxima execução
            self._rebuild_mic_menu()
        return _pick

    def _pick_auto(self, _sender):
        self.device_manual = False
        self.device_index = None
        self.device_name = None
        self.device_is_bluetooth = False
        save_device_choice(None)  # esquece escolha manual salva antes
        self._rebuild_mic_menu()

    def _resolve_device(self):
        """
        Garante que self.device_index aponte pra algo antes de abrir o
        stream de áudio. Retorna True se conseguiu, False se não achou
        nada (nem manual, nem preferido, nem o padrão do sistema).

        Se a pessoa escolheu manualmente (device_manual), re-resolve o
        índice pelo NOME salvo a cada chamada via
        audio_input.resolve_device_by_name() — NÃO reaproveita
        cegamente o índice guardado (ver docstring de lá pro porquê:
        índice de sounddevice não é estável entre trocas de topologia).

        Senão (modo automático), escaneia DE NOVO a cada chamada — não
        reaproveita um valor decidido lá no __init__, de propósito: a
        pessoa pode ligar/parear o fone Bluetooth DEPOIS de abrir o
        vIsper, e a próxima vez que clicar em "Start listening" já deve
        encontrar.
        """
        if self.device_manual:
            index = resolve_device_by_name(self.device_name)
            if index is None:
                return False
            self.device_index = index
            # Reclassifica a cada resolve, não só na hora do clique: é
            # o único ponto por onde uma escolha manual RESTAURADA de
            # outra execução passa antes de abrir o stream (ver
            # __init__).
            self.device_is_bluetooth = classify_device(self.device_name)
            return True

        # Preferidos primeiro (DJI, fone Bluetooth); se nenhum estiver
        # por perto, o microfone padrão do sistema. Sem esse segundo
        # passo, abrir o vIsper sem o DJI plugado respondia a "Start
        # listening" com um alerta e mais nada — dava a impressão de que
        # o app não funciona, com o mic embutido do Mac ali o tempo todo.
        found = guess_preferred_device() or default_input_device()
        if not found:
            return False
        self.device_index, self.device_name, self.device_is_bluetooth = found
        return True

    # ------------------------------------------------------------------
    # Escuta
    # ------------------------------------------------------------------

    @rumps.clicked("Start listening")
    def start_listening(self, _):
        if self.listening:
            return
        # "Stop listening" só baixa a flag; a thread antiga ainda pode
        # estar dentro de um stream.read() de até chunk_seconds. Sem
        # esse guard, clicar Stop e Start em seguida abria uma SEGUNDA
        # thread (self.listening já era False) — duas transcrições
        # paralelas alimentando o mesmo DictationSession, com ditado
        # duplicado e fechamento na hora errada.
        if self._listen_thread is not None and self._listen_thread.is_alive():
            notify(
                "vIsper",
                "Still stopping",
                "The previous session is finishing its current chunk — "
                "try again in a few seconds.",
            )
            return

        # O modelo carrega em segundo plano (ver __init__). Clicar antes
        # dele ficar pronto é normal na primeira execução, quando são
        # ~150 MB de download — então isso explica em vez de falhar.
        if self.model is None:
            if self.model_error:
                rumps.alert(
                    "vIsper could not load the speech model.\n\n"
                    f"{self.model_error}\n\n"
                    "Check your internet connection and reopen vIsper — "
                    "the model is downloaded once and then cached."
                )
            else:
                notify(
                    "vIsper",
                    "Still getting ready",
                    "Downloading the speech model (about 150 MB, first run "
                    "only). The icon turns into a microphone when it's done.",
                )
            return

        self._rebuild_mic_menu()
        if not self._resolve_device():
            if self.device_manual:
                rumps.alert(
                    f"The microphone you picked ('{self.device_name}') is not "
                    "connected right now. Reconnect it, pick another one under "
                    "'Microphone', or switch back to 'Detect automatically'."
                )
            else:
                rumps.alert(
                    "vIsper could not find any microphone on this Mac. "
                    "Check System Settings › Sound › Input, then try again."
                )
            return
        if self.device_is_bluetooth:
            # Aviso de qualidade, não bloqueante — o Bluetooth clássico
            # derruba o áudio do SISTEMA INTEIRO (não só a gravação) pra
            # mono/qualidade de ligação enquanto o stream de entrada
            # estiver aberto. Ver README, seção "Sobre usar fone de
            # ouvido". Mostrado uma vez por sessão de escuta (não por
            # chunk), mesmo padrão de notificação que o resto do app já
            # usa pra status.
            notify(
                "vIsper",
                "Bluetooth microphone",
                f"Using {self.device_name}. System audio may drop to call "
                "quality (mono) while listening — that's how Bluetooth "
                "works, not a bug.",
            )
        self.listening = True
        self._set_state("listening")
        self._listen_thread = threading.Thread(
            target=self._listen_loop_safe, daemon=True
        )
        self._listen_thread.start()

    @rumps.clicked("Stop listening")
    def stop_listening(self, _):
        self.listening = False
        self._set_state("stopped")

    @rumps.clicked("Quit vIsper")
    def quit_app(self, _):
        # quit_button=None no super().__init__ e um item próprio aqui:
        # sair precisa baixar a flag de escuta antes, senão a thread de
        # áudio pode continuar segurando o microfone (e, com fone
        # Bluetooth, mantendo o áudio do sistema em mono) depois do app
        # sumir da barra de menu.
        self.listening = False
        rumps.quit_application()

    def _play_dictation_sound(self, sound_name):
        """Earcon de abrir/mandar ditado (config.DICTATION_*_SOUND) —
        respeita DICTATION_SOUNDS_ENABLED. Mais útil ainda com fone de
        ouvido: dá pra saber que abriu/mandou sem olhar pra barra de
        menu (ex.: durante o treino)."""
        if config.DICTATION_SOUNDS_ENABLED:
            actions.play_sound(sound_name)

    # ------------------------------------------------------------------
    # Configuração pelo próprio app
    #
    # Instalada pelo .dmg, a pessoa não tem Terminal nem a pasta do
    # projeto — `python3 setup_visper.py` simplesmente não é alcançável.
    # Sem isto, o caminho "sem atrito" era o único SEM jeito de
    # configurar o iPhone.
    # ------------------------------------------------------------------

    @rumps.clicked("Settings…")
    def open_settings(self, _):
        topico = config.NTFY_TOPIC
        resumo = topico if topico else "(off — iPhone can't reach this Mac)"
        janela = rumps.Window(
            title="vIsper settings",
            message=(
                "Wake word: "
                f"{config.WAKE_WORD}\n"
                f"iPhone topic: {resumo}\n\n"
                "Paste a new iPhone topic below to change it, or leave it "
                "empty and press OK to keep things as they are.\n\n"
                "This topic is a password: anyone who knows it can type "
                "into this Mac. Generate one with setup_visper.py, or paste "
                "the one you already use on your phone.\n\n"
                f"Saved in: {settings_path()}"
            ),
            default_text="",
            ok="Save",
            cancel="Cancel",
            dimensions=(340, 24),
        )
        resposta = janela.run()
        if not resposta.clicked:
            return

        novo = resposta.text.strip()
        if not novo:
            return
        # Tolera colar a URL inteira do ntfy — é o erro mais provável, e
        # dá pra corrigir sozinho em vez de falhar em silêncio depois.
        novo = re.sub(r"^https?://ntfy\.sh/", "", novo).strip("/")

        if save_settings({"NTFY_TOPIC": novo}):
            rumps.alert(
                "Saved. Quit and reopen vIsper for the iPhone connection "
                "to start using the new topic."
            )
        else:
            rumps.alert(
                "Could not write the settings file:\n" f"{settings_path()}"
            )

    # ------------------------------------------------------------------
    # Loops
    # ------------------------------------------------------------------

    def _relay_loop(self):
        self.relay.listen_forever(on_result=self._on_result)

    def _on_result(self, resultado):
        """Retorno único pros dois caminhos de entrada (mic e iPhone)."""
        if not resultado:
            return
        notify("vIsper", "Status", resultado)
        # A máquina de estados é a fonte da verdade: depois de mandar,
        # a sessão volta pra ociosa, e o ícone tem que acompanhar. O
        # 🔵 de "mandou" é posto por _on_dictation_send e fica até a
        # próxima transição.
        if self.session.dictating:
            self._set_state("dictating")
        elif self.listening and self.title != STATE_GLYPHS["sent"]:
            self._set_state("listening")

    def _listen_loop_safe(self):
        """
        Envolve _listen_loop() num try/except. Sem isso, se o stream de
        áudio falhasse ao abrir (ex.: o dispositivo escolhido manualmente
        desconectou entre o clique e agora — cenário bem mais comum com
        fone Bluetooth do que com o DJI cabeado), a thread morria calada
        (só um traceback no stderr) e self.listening ficava travado em
        True pra sempre: "Start listening" parecia não fazer nada (o guard
        `if self.listening: return` no topo do método barra) e só
        reiniciar o app resolvia. Agora cai pra idle e avisa.
        """
        try:
            self._listen_loop()
        except actions.AutomationDenied as exc:
            # Falha de PERMISSÃO não é falha de áudio. Antes as duas
            # caíam no mesmo "Erro no áudio: ...", que mandava ela
            # investigar o microfone quando o problema era o macOS ainda
            # não ter autorizado o vIsper a controlar outros apps — o
            # erro mais provável de todos na primeira execução, e o
            # único cuja correção é um caminho fixo de Ajustes.
            self.listening = False
            self._set_state("error")
            rumps.alert(
                "vIsper needs Accessibility permission to type into your AI "
                "chat.\n\n"
                "Open System Settings › Privacy & Security › Accessibility "
                "and turn vIsper on, then start listening again.\n\n"
                f"({exc})"
            )
        except Exception as exc:
            self.listening = False
            self._set_state("error")
            notify("vIsper", "Listening stopped", f"Audio error: {exc}")

    def _listen_loop(self):
        if self.porcupine_detector and self.porcupine_detector.enabled:
            self._listen_loop_porcupine()
        else:
            self._listen_loop_whisper(AudioStream(self.device_index))

    def _listen_loop_whisper(self, stream):
        for chunk in stream.chunks():
            if not self.listening:
                break
            segments, _info = self.model.transcribe(
                chunk,
                language=LANGUAGE,
                # vad_filter descarta o que não for fala antes de
                # transcrever. Sem ele, o Whisper ALUCINA em cima de
                # silêncio e ruído — costuma devolver frases inteiras
                # ("Legendas pela comunidade Amara.org", "Obrigado por
                # assistir") que vinham de vídeo legendado no treino
                # dele. Num app que escuta o tempo todo isso não é
                # detalhe: texto inventado entra no ditado como se fosse
                # fala real, e uma alucinação que contenha a wake word
                # ou "over" dispara ação sozinha.
                vad_filter=True,
            )
            # Mesma correção de audio_file_input.py: os segmentos já
            # vêm com espaço embutido, " ".join() duplicava.
            text = re.sub(r"\s+", " ", "".join(seg.text for seg in segments)).strip()
            if text:
                self._set_heard(text)
            self._on_result(self.session.handle(text))

    def _listen_loop_porcupine(self):
        # NUNCA TESTADO COM MIC/HARDWARE DE VERDADE — a lógica de
        # estados (porcupine_session.py) tem 4 testes passando com
        # tudo simulado, mas essa junção com o InputStream real do
        # sounddevice e o loop do rumps é nova e ainda não validada
        # numa máquina real. Primeira coisa a testar depois de rodar a
        # v1 (Whisper contínuo) com sucesso.
        self.porcupine_detector.start()
        try:
            # O stream é aberto DEPOIS do start() e na taxa que o
            # próprio Porcupine exige, em vez do padrão do AudioStream:
            # ele é rígido quanto a isso (áudio em outra taxa não dá
            # erro, só nunca detecta nada) e a taxa dele só existe
            # depois que o motor é criado.
            stream = AudioStream(
                self.device_index,
                samplerate=self.porcupine_detector.sample_rate,
            )
            frames = stream.raw_frames(self.porcupine_detector.frame_length)

            def gated_frames():
                for frame in frames:
                    if not self.listening:
                        return
                    yield frame

            ps = PorcupineSession(
                self.porcupine_detector,
                self.model,
                self.session,
                sample_rate=self.porcupine_detector.sample_rate,
                language=LANGUAGE,
            )
            ps.run(gated_frames(), on_result=self._on_result)
        finally:
            self.porcupine_detector.stop()


if __name__ == "__main__":
    VisperApp().run()

"""
vIsper — lançador ativado por voz + interface completa de ditado.

Dois caminhos de escuta, escolhidos automaticamente:
  - Sem PORCUPINE_ACCESS_KEY/PORCUPINE_KEYWORD_PATH em config.py:
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
reconhecidos automaticamente via config.PREFERRED_INPUT_DEVICES — ver
audio_input.py. Dá pra escolher manualmente no submenu "Escolher
microfone" também, se a auto-detecção não pegar o dispositivo certo.

É um app de menu bar (rumps), então fica discreto. Clique no ícone na
barra de menu pra escolher o microfone, iniciar/parar escuta, ou sair.
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
    classify_device,
    resolve_device_by_name,
    load_saved_device_name,
    save_device_choice,
)
from command_router import CommandRouter
from dictation import DictationSession
from relay_listener import RelayListener
from wake_word_porcupine import PorcupineWakeWordDetector
from porcupine_session import PorcupineSession
import actions
import config


MODEL_SIZE = "base"  # tiny/base/small — maior = mais preciso, mais lento
# language=None deixa o Whisper detectar o idioma a cada trecho, pra
# funcionar em português, inglês, ou qualquer outro que você fale.
LANGUAGE = None


class VisperApp(rumps.App):
    def __init__(self):
        super().__init__("vIsper", icon=None, quit_button="Sair")
        self.router = CommandRouter(actions.AI_ACTIONS)
        self.session = DictationSession(
            router=self.router,
            paste_action=actions.paste_text,
            send_action=actions.handle_done,
            on_open=lambda: self._play_dictation_sound(config.DICTATION_OPEN_SOUND),
            on_send=lambda: self._play_dictation_sound(config.DICTATION_SEND_SOUND),
        )
        self.model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
        self.listening = False

        # Dispositivo de entrada: começa em modo AUTOMÁTICO (device_index
        # None = "detecta de novo, do zero, na próxima vez que precisar" —
        # ver _resolve_device()). Vira manual assim que a pessoa escolhe
        # algo no submenu "Escolher microfone"; volta a automático se ela
        # clicar em "Detectar automaticamente" lá dentro. Cada escolha
        # manual é lembrada entre execuções (audio_input.DEVICE_STATE_PATH)
        # — se existir uma salva, já começa em modo manual com ela; o
        # ÍNDICE só é resolvido de verdade quando precisar (_resolve_device),
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

        # Relay do iPhone via ntfy — só liga se um tópico de verdade
        # estiver configurado em config.py (o placeholder é ""). Roda
        # numa thread própria, independente da escuta do mic local:
        # os dois alimentam o mesmo self.session, então "abrir pelo
        # Mac" e "abrir pelo iPhone" nunca ficam em estados diferentes.
        self.relay = None
        if config.NTFY_TOPIC:
            self.relay = RelayListener(self.session, topic=config.NTFY_TOPIC)
            threading.Thread(target=self._relay_loop, daemon=True).start()

        # Wake word acústica (opcional) — ver porcupine_session.py.
        # Só ativa se as duas chaves estiverem em config.py; senão o
        # loop de mic local continua no modo Whisper contínuo de hoje.
        self.porcupine_detector = None
        if config.PORCUPINE_ACCESS_KEY and config.PORCUPINE_KEYWORD_PATH:
            self.porcupine_detector = PorcupineWakeWordDetector(
                access_key=config.PORCUPINE_ACCESS_KEY,
                keyword_path=config.PORCUPINE_KEYWORD_PATH,
            )

        self.mic_menu = rumps.MenuItem("Escolher microfone")
        self.menu = [self.mic_menu, "Iniciar escuta", "Parar escuta"]
        self._rebuild_mic_menu()

    # ------------------------------------------------------------------
    # Seleção de microfone — automática (padrão, DJI > fone Bluetooth,
    # ver config.PREFERRED_INPUT_DEVICES) ou manual via submenu.
    #
    # NUNCA TESTADO num Mac de verdade, como o resto deste arquivo: a
    # API de submenu dinâmico do rumps usada abaixo (MenuItem.clear()/
    # .add(), estado de checkmark via .state, título mutável via
    # .title) foi conferida linha a linha contra o SOURCE real do
    # pacote (rumps==0.4.0, baixado da PyPI — não só documentação nem
    # de memória), mas isso não substitui ver o AppKit/NSMenu de
    # verdade renderizar o menu. Primeira coisa a olhar se "Escolher
    # microfone" não aparecer certo na barra de menu.
    # ------------------------------------------------------------------

    def _rebuild_mic_menu(self):
        """Repopula o submenu a partir dos dispositivos ATUALMENTE
        conectados — chamado no __init__ e de novo toda vez que algo
        pode ter mudado (escolha manual, voltou pro automático, ou
        logo antes de tentar escutar), pra refletir fone Bluetooth
        ligado/desligado depois que o app já abriu."""
        self.mic_menu.clear()

        auto_item = rumps.MenuItem(
            "Detectar automaticamente", callback=self._pick_auto
        )
        auto_item.state = not self.device_manual
        self.mic_menu.add(auto_item)

        # label_devices() desambigua o RÓTULO exibido quando dois
        # dispositivos têm o MESMO nome — sem isso, rumps (que indexa
        # o submenu pelo título) faria o segundo simplesmente sumir do
        # menu. Ver docstring de audio_input.label_devices() pro
        # raciocínio completo (inclui a limitação aceita: seleção
        # continua por nome puro, não pelo rótulo desambiguado).
        for index, name, label in label_devices(list_input_devices()):
            item = rumps.MenuItem(label, callback=self._make_pick_device(index, name))
            # Compara por NOME, não índice: logo depois de carregar uma
            # escolha salva (__init__), device_index ainda é None (só é
            # resolvido de verdade na primeira vez que precisar) — comparar
            # por índice deixaria o checkmark faltando até o primeiro
            # "Iniciar escuta". Por nome funciona desde o primeiro rebuild.
            item.state = self.device_manual and name == self.device_name
            self.mic_menu.add(item)

        if self.device_name:
            self.mic_menu.title = f"Microfone: {self.device_name}"
        else:
            self.mic_menu.title = "Escolher microfone"

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
        nada (nem auto, nem escolha manual válida).

        Se a pessoa escolheu manualmente (device_manual), re-resolve o
        índice pelo NOME salvo a cada chamada via
        audio_input.resolve_device_by_name() — NÃO reaproveita
        cegamente o índice guardado (ver docstring de lá pro porquê:
        índice de sounddevice não é estável entre trocas de topologia).

        Senão (modo automático), escaneia DE NOVO a cada chamada — não
        reaproveita um valor decidido lá no __init__, de propósito: a
        pessoa pode ligar/parear o fone Bluetooth DEPOIS de abrir o
        vIsper, e a próxima vez que clicar em "Iniciar escuta" já deve
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

        found = guess_preferred_device()
        if not found:
            return False
        self.device_index, self.device_name, self.device_is_bluetooth = found
        return True

    @rumps.clicked("Iniciar escuta")
    def start_listening(self, _):
        if self.listening:
            return
        # "Parar escuta" só baixa a flag; a thread antiga ainda pode
        # estar dentro de um stream.read() de até chunk_seconds. Sem
        # esse guard, clicar Parar e Iniciar em seguida abria uma
        # SEGUNDA thread (self.listening já era False) — duas
        # transcrições paralelas alimentando o mesmo DictationSession,
        # com ditado duplicado e fechamento na hora errada.
        if self._listen_thread is not None and self._listen_thread.is_alive():
            rumps.notification(
                "vIsper",
                "Ainda parando",
                "A escuta anterior está terminando o trecho atual — tente de "
                "novo em alguns segundos.",
            )
            return
        self._rebuild_mic_menu()
        if not self._resolve_device():
            if self.device_manual:
                rumps.alert(
                    f"O microfone escolhido ('{self.device_name}') não está "
                    "conectado agora. Reconecte ele, escolha outro no menu "
                    "'Escolher microfone', ou volte pra 'Detectar "
                    "automaticamente' lá dentro."
                )
            else:
                rumps.alert(
                    "Nenhum microfone reconhecido automaticamente (ver "
                    "config.PREFERRED_INPUT_DEVICES — hoje: DJI Mic ou fone "
                    "Bluetooth tipo Sony XM5). Confira se está ligado/pareado, "
                    "ou escolha manualmente no menu 'Escolher microfone'."
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
            rumps.notification(
                "vIsper",
                "Microfone Bluetooth",
                f"Usando {self.device_name}. O áudio do sistema pode cair "
                "pra qualidade de ligação (mono) enquanto a escuta estiver "
                "ativa — é do protocolo Bluetooth, não um bug do app.",
            )
        self.listening = True
        self._listen_thread = threading.Thread(
            target=self._listen_loop_safe, daemon=True
        )
        self._listen_thread.start()

    @rumps.clicked("Parar escuta")
    def stop_listening(self, _):
        self.listening = False

    def _play_dictation_sound(self, sound_name):
        """Earcon de abrir/mandar ditado (config.DICTATION_*_SOUND) —
        respeita DICTATION_SOUNDS_ENABLED. Mais útil ainda com fone de
        ouvido: dá pra saber que abriu/mandou sem olhar pra barra de
        menu (ex.: durante o treino)."""
        if config.DICTATION_SOUNDS_ENABLED:
            actions.play_sound(sound_name)

    def _relay_loop(self):
        self.relay.listen_forever(
            on_result=lambda r: rumps.notification("vIsper (iPhone)", "Status", r)
        )

    def _listen_loop_safe(self):
        """
        Envolve _listen_loop() num try/except. Sem isso, se o stream de
        áudio falhasse ao abrir (ex.: o dispositivo escolhido manualmente
        desconectou entre o clique e agora — cenário bem mais comum com
        fone Bluetooth do que com o DJI cabeado), a thread morria calada
        (só um traceback no stderr) e self.listening ficava travado em
        True pra sempre: "Iniciar escuta" parecia não fazer nada (o guard
        `if self.listening: return` no topo do método barra) e só
        reiniciar o app resolvia. Agora cai pra idle e avisa por
        notificação, do mesmo jeito que qualquer outro status do app.
        """
        try:
            self._listen_loop()
        except Exception as exc:
            self.listening = False
            rumps.notification("vIsper", "Escuta parou", f"Erro no áudio: {exc}")

    def _listen_loop(self):
        if self.porcupine_detector and self.porcupine_detector.enabled:
            self._listen_loop_porcupine()
        else:
            self._listen_loop_whisper(AudioStream(self.device_index))

    def _listen_loop_whisper(self, stream):
        for chunk in stream.chunks():
            if not self.listening:
                break
            segments, _info = self.model.transcribe(chunk, language=LANGUAGE)
            # Mesma correção de audio_file_input.py: os segmentos já
            # vêm com espaço embutido, " ".join() duplicava.
            text = re.sub(r"\s+", " ", "".join(seg.text for seg in segments)).strip()
            result = self.session.handle(text)
            if result:
                rumps.notification("vIsper", "Status", result)

    def _listen_loop_porcupine(self):
        # NUNCA TESTADO COM MIC/HARDWARE DE VERDADE — a lógica de
        # estados (porcupine_session.py) tem 4 testes passando com
        # tudo simulado, mas essa junção com o InputStream real do
        # sounddevice e o loop do rumps é nova e ainda não validada
        # numa máquina real. Primeira coisa a testar no Claude Code
        # depois de rodar a v1 (Whisper contínuo) com sucesso.
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
            ps.run(
                gated_frames(),
                on_result=lambda r: rumps.notification("vIsper", "Status", r),
            )
        finally:
            self.porcupine_detector.stop()


if __name__ == "__main__":
    VisperApp().run()

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

import os
import re
import threading
import time
from collections import deque
import rumps
from faster_whisper import WhisperModel
from PyObjCTools import AppHelper

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

# Quantas linhas de "o que ouvi / o que decidi" ficam guardadas pra
# "Recent activity…". Só na MEMÓRIA, nunca em disco: o app escuta o
# tempo todo, então gravar transcrição em arquivo seria uma mudança de
# privacidade que ninguém pediu — e pra diagnosticar não é preciso,
# porque a dúvida ("por que não funcionou agora?") é sempre sobre o
# passado recente. 25 linhas cobrem bem mais que 25 trechos de tempo:
# trecho silencioso não transcreve nada e não entra aqui.
#
# O teto é baixo porque a janela é um NSAlert (rumps.alert()), que
# cresce junto com o texto e não rola: guardar 40 linhas compridas
# renderia um alerta mais alto que a tela — inútil justamente no
# momento em que ele precisa ser lido.
HISTORY_MAX = 25

# Linha mais comprida que isso é encurtada NO MEIO na hora de mostrar.
# No meio, não no fim, de propósito: as duas pontas de uma linha
# `heard` são exatamente os dois pontos de diagnóstico — a wake word
# abre a frase e o gatilho de fechamento ("over"/"câmbio") fecha. Cortar
# o fim jogaria fora metade da resposta.
HISTORY_LINE_MAX = 110

# ---------------------------------------------------------------------
# ESTADOS — o que aparece na barra de menu.
#
# Antes o título era fixo ("vIsper") e o único retorno era notificação,
# que some sozinha em segundos. Não dava pra responder a pergunta mais
# básica de todas — "ele está me ouvindo agora?" — sem falar uma frase
# de teste e torcer.
#
# A SILHUETA DO MASCOTE colorida, não emoji e não um círculo liso.
# Dois eixos que comunicam coisas diferentes: a FORMA é sempre a
# mesma (o desenho de design/menubar_icon_template.svg — é o que
# identifica o vIsper entre os outros ícones da barra), e só a COR
# muda com o estado.
#
# As duas versões anteriores erraram um eixo cada. Emoji
# (⏳🎙🟢🔴🔵🟠) como TÍTULO: as cores eram as do FONTE DE EMOJI da
# Apple, não as da paleta documentada (design/layouts_mockup.html) —
# 🟠 não é terracota, 🎙 não tem cor de estado nenhuma. Círculo
# sólido: cor certa, identidade jogada fora. As cores abaixo são as
# MESMAS (mesmo hex) do mockup — cinza=parado, âmbar=carregando,
# verde=escutando, coral=ditando, azul=mandou, terracota=erro.
#
# Os PNGs (status_icons/, gerados por
# design/generate_status_icons.py) entram SEM modo template: template
# forçaria monocromático (preto/branco conforme claro/escuro) e a cor
# documentada sumiria de novo — o mesmo problema do emoji, só que por
# outro caminho.
# ---------------------------------------------------------------------
_ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "status_icons")
STATUS_ICONS = {
    "stopped": os.path.join(_ICON_DIR, "stopped.png"),      # parado — mas vivo
    "loading": os.path.join(_ICON_DIR, "loading.png"),      # carregando o modelo
    "listening": os.path.join(_ICON_DIR, "listening.png"),  # esperando a wake word
    "dictating": os.path.join(_ICON_DIR, "dictating.png"),  # acumulando o ditado
    "sent": os.path.join(_ICON_DIR, "sent.png"),            # acabou de colar e mandar
    "error": os.path.join(_ICON_DIR, "error.png"),          # o menu explica o quê
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


def _elide(linha, limite=HISTORY_LINE_MAX):
    """Encurta uma linha comprida PELO MEIO — ver HISTORY_LINE_MAX."""
    if len(linha) <= limite:
        return linha
    # Sobra mais pro começo: é onde está o horário, o marcador e a wake
    # word. O fim guarda só o suficiente pra mostrar como a frase
    # terminou (o gatilho de fechamento mora ali).
    fim = 40
    inicio = limite - fim - 3
    return f"{linha[:inicio]}...{linha[-fim:]}"


class VisperApp(rumps.App):
    def __init__(self):
        # name="vIsper" (não mais o glifo de estado): rumps usa esse
        # valor pra nomear a pasta de Application Support dele
        # (rumps.application_support) — deixar um caractere de estado
        # ali criaria (inofensivamente, mas sem sentido) uma pasta com
        # nome de emoji. icon= já entra com o ícone de "carregando":
        # sem isso o app ficava com o nome como texto até o primeiro
        # _set_state(), um instante de UI errada.
        super().__init__(
            "vIsper", icon=STATUS_ICONS["loading"], title=None, quit_button=None
        )
        # Rastreado à parte de self.icon/self.title de propósito — ver
        # _set_state(). A atualização REAL do AppKit é assíncrona
        # (despachada pra thread principal); reler self.icon logo
        # depois de chamar _set_state() pegaria o valor ANTIGO.
        self._current_state = "loading"
        self.router = CommandRouter(actions.AI_ACTIONS)
        self.session = DictationSession(
            router=self.router,
            paste_action=actions.paste_text,
            send_action=actions.handle_done,
            on_open=self._on_dictation_open,
            on_send=self._on_dictation_send,
            on_cancel=self._on_dictation_cancel,
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

        # Vocabulário de comando que o transcritor deve PRIORIZAR —
        # metade da melhoria de detecção (a outra é o casamento
        # tolerante do command_router). Calculado uma vez: config já
        # está com o settings.json aplicado aqui.
        self._hotwords = config.transcription_hotwords()

        # Idiomas que ela fala (ver config.TRANSCRIPTION_LANGUAGES).
        # Um só = força ele e pula a detecção. Vários = detecta mas
        # valida contra a lista. Nenhum = sem restrição.
        # Último idioma que passou na validação — vira o idioma de
        # reserva quando a detecção sai da lista ou vem insegura.
        # Melhor reserva do que o primeiro da lista: pessoa não troca
        # de idioma a cada 4 segundos, então "o que estava valendo
        # agora há pouco" acerta bem mais que um padrão fixo.
        self._last_good_language = None
        self._apply_languages(config.TRANSCRIPTION_LANGUAGES)

        # Última coisa que o Whisper entendeu. Fica visível no menu
        # porque a falha mais confusa deste app é a wake word ser
        # transcrita errada: sem isso, "ele não me ouve" e "ele me ouviu
        # mas escreveu 'visper' com v minúsculo" são indistinguíveis, e
        # a segunda é a mais provável (a wake word padrão é uma palavra
        # inventada — ver "Limite atual do reconhecimento" no README).
        self._last_heard = ""
        # O "Heard:" acima mostra só o ÚLTIMO trecho, cortado em 45
        # caracteres — some assim que chega o próximo. Isso basta pra
        # "ele está me ouvindo?", mas não pra "falei o comando faz 30
        # segundos e não aconteceu nada, o que ele entendeu?": quando
        # ela abre o menu, a prova já foi sobrescrita. Este histórico é
        # a resposta dessa segunda pergunta — ver HISTORY_MAX.
        #
        # deque(maxlen=...) é escrito pelas threads de escuta e lido
        # pela thread principal (o @rumps.clicked). Não leva lock de
        # propósito: append/list numa deque são atômicos no CPython, e
        # o pior caso possível aqui seria uma linha entrar fora de
        # ordem — irrelevante pra diagnóstico, e bem melhor que segurar
        # um lock dentro do laço de transcrição.
        self._history = deque(maxlen=HISTORY_MAX)
        # Timer que desfaz um estado momentâneo (hoje só o "mandou") —
        # ver _flash_state(). Um por vez; começar outro cancela o
        # anterior.
        self._revert_timer = None

        self.mic_menu = rumps.MenuItem("Microphone")
        # Ver o guard em _rebuild_mic_menu(): o rumps só cria o NSMenu
        # interno do submenu no primeiro .add() — antes disso,
        # MenuItem.clear() explode tentando limpar um menu que ainda
        # não existe. Essa flag é o que diferencia "primeira vez" de
        # "reconstruindo".
        self._mic_menu_populated = False
        self.heard_item = rumps.MenuItem("Heard: —", callback=None)
        self.menu = [
            self.heard_item,
            "Recent activity…",
            None,
            "Start listening",
            "Stop listening",
            None,
            self.mic_menu,
            "Wake word…",
            "Spoken languages…",
            "iPhone connection…",
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
        """
        Troca o ícone colorido da barra de menu. Ver STATUS_ICONS.

        SEMPRE despachado pra thread principal via AppHelper.callAfter
        — bug real, achado rodando de verdade: main.py chama isto de
        THREADS DE FUNDO o tempo todo (_load_model, _listen_loop_*,
        _on_result vindo do relay do iPhone), e mexer em NSStatusItem
        fora da main thread é uma violação de verdade do AppKit
        ("Must only be used from the main thread") — crashava na hora
        que a pessoa tinha o menu ABERTO enquanto uma dessas threads
        tentava atualizar o ícone por baixo. AppHelper.callAfter (do
        PyObjCTools que já vem com pyobjc-framework-Cocoa, dependência
        do próprio rumps — nada novo pra instalar) resolve isso do
        jeito padrão: `performSelectorOnMainThread_withObject_
        waitUntilDone_`, o mesmo mecanismo que qualquer app PyObjC
        usa. Seguro chamar daqui até da própria main thread (só enfileira
        pro próximo ciclo do runloop).
        """
        self._current_state = state
        icon_path = STATUS_ICONS.get(state, STATUS_ICONS["stopped"])
        AppHelper.callAfter(setattr, self, "icon", icon_path)

    def _flash_state(self, state, seconds=2.5):
        """Mostra um estado por alguns segundos e volta pro que a
        situação REAL manda.

        Existe porque "mandou" (azul) é um EVENTO, não uma situação: o
        app continua escutando logo depois. Sem isso o azul ficava até
        a próxima coisa acontecer — podiam ser minutos —, e o ícone
        passava esse tempo todo respondendo errado a pergunta que ele
        existe pra responder ("ele está me ouvindo agora?").

        `_current_state` é relido na hora de voltar, não capturado
        agora: entre o flash e o timer a pessoa pode ter apertado
        "Stop listening", começado outro ditado, ou dado erro — e
        nenhum desses pode ser desfeito por um timer velho.
        """
        self._set_state(state)
        if self._revert_timer is not None:
            self._revert_timer.cancel()

        def voltar():
            # A referência do timer NÃO é limpa aqui de propósito:
            # cancel() num Timer que já disparou é inofensivo, e
            # deixar a referência viva é o que permite esperar por ele
            # (nos testes) sem corrida.
            #
            # Só desfaz o PRÓPRIO flash: se o estado já mudou, quem
            # mudou tem mais razão que este timer.
            if self._current_state != state:
                return
            if self.session.dictating:
                self._set_state("dictating")
            else:
                self._set_state("listening" if self.listening else "stopped")

        self._revert_timer = threading.Timer(seconds, voltar)
        # Daemon: um timer pendente não pode segurar o processo aberto
        # depois de "Quit vIsper".
        self._revert_timer.daemon = True
        self._revert_timer.start()

    def _log_activity(self, marker, texto):
        """Guarda uma linha no histórico de "Recent activity…".

        Só memória, nunca disco — ver HISTORY_MAX. Chamado das threads
        de escuta, mas NÃO precisa de AppHelper.callAfter: não toca em
        nada do AppKit, só numa deque de Python. A regra da thread
        principal vale pra MUTAÇÃO DE UI, e aqui não há nenhuma.
        """
        if not texto:
            return
        self._history.append(f"{time.strftime('%H:%M:%S')}  {marker}  {texto}")

    def _set_heard(self, texto):
        """Mostra no menu o que o Whisper entendeu por último. Mesmo
        motivo de _set_state() pra despachar via callAfter — chamado
        de _listen_loop_whisper() e _load_model(), as duas threads de
        fundo."""
        self._last_heard = texto or ""
        self._log_activity("heard", self._last_heard)
        curto = self._last_heard[:45] + ("…" if len(self._last_heard) > 45 else "")
        label = f"Heard: {curto}" if curto else "Heard: —"
        AppHelper.callAfter(setattr, self.heard_item, "title", label)

    def _on_dictation_open(self):
        self._set_state("dictating")
        self._play_dictation_sound(config.DICTATION_OPEN_SOUND)

    def _on_dictation_send(self):
        # Flash, não estado fixo: mandar é um evento e a escuta segue —
        # ver _flash_state().
        self._flash_state("sent")
        self._play_dictation_sound(config.DICTATION_SEND_SOUND)

    def _on_dictation_cancel(self):
        """"vIsper, cancela" — o ditado foi jogado fora, nada foi
        mandado. Volta direto pro estado de escuta (não passa por
        "sent", que quer dizer o oposto) e toca um som DIFERENTE: se
        cancelar soasse igual a mandar, a dúvida que o cancelamento
        existe pra tirar continuaria de pé."""
        self._set_state("listening" if self.listening else "stopped")
        self._play_dictation_sound(config.DICTATION_CANCEL_SOUND)

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
    # A API de submenu dinâmico do rumps usada abaixo (MenuItem.clear()/
    # .add(), estado de checkmark via .state, título mutável via
    # .title) foi conferida linha a linha contra o SOURCE real do
    # pacote (rumps==0.4.0, baixado da PyPI — não só documentação nem
    # de memória). Mas ISSO NÃO PEGOU um detalhe de TIMING que só um
    # Mac de verdade revelou: MenuItem.clear() chama
    # `self._menu.removeAllItems()`, e `self._menu` (o NSMenu do
    # submenu) só é criado dentro do rumps na hora do PRIMEIRO
    # `.add()` — antes disso ele é `None`. Chamar `.clear()` num
    # MenuItem que nunca recebeu um `.add()` (exatamente o caso da
    # primeiríssima chamada, vinda do `__init__`) levantava
    # `AttributeError: 'NoneType' object has no attribute
    # 'removeAllItems'` e derrubava o app ANTES do ícone existir — a
    # categoria de bug mais grave que existe aqui, porque sem Terminal
    # não sobra rastro nenhum. Confirmado rodando de verdade.
    # ------------------------------------------------------------------

    def _rebuild_mic_menu(self):
        """Repopula o submenu a partir dos dispositivos ATUALMENTE
        conectados — chamado no __init__ e de novo toda vez que algo
        pode ter mudado (escolha manual, voltou pro automático, ou
        logo antes de tentar escutar), pra refletir fone Bluetooth
        ligado/desligado depois que o app já abriu."""
        if self._mic_menu_populated:
            self.mic_menu.clear()

        auto_item = rumps.MenuItem("Detect automatically", callback=self._pick_auto)
        auto_item.state = not self.device_manual
        self.mic_menu.add(auto_item)
        # A partir daqui o NSMenu interno já existe (foi criado por
        # esse .add() de cima) — chamadas futuras a _rebuild_mic_menu()
        # já podem chamar .clear() com segurança.
        self._mic_menu_populated = True

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

    def _apply_languages(self, idiomas):
        """Passa a valer a lista de idiomas — do __init__ ou do menu.

        Num método só (em vez de repetido nos dois lugares) porque as
        três coisas derivadas têm que mudar JUNTAS: com um idioma só,
        `_forced_language` pula a detecção; com vários ela é validada
        contra `_allowed_languages`; e o idioma de reserva guardado de
        antes pode nem estar na lista nova, então é zerado.
        """
        self._allowed_languages = list(idiomas or [])
        self._forced_language = (
            self._allowed_languages[0] if len(self._allowed_languages) == 1 else None
        )
        self._last_good_language = None

    def _ask(self, title, message, default_text=""):
        """Uma caixa de texto do rumps, com o valor atual já dentro.

        Existe porque configurar pelo menu NÃO pode depender de
        Terminal: quem instalou pelo .dmg não tem o repositório nem o
        setup_visper.py na máquina — mandar essa pessoa "editar o
        config.py" é exatamente o atrito que o .dmg foi feito pra
        tirar.

        Devolve None se cancelou, ou o texto (já aparado) se
        confirmou. Roda sempre a partir de um @rumps.clicked, ou seja,
        já na thread principal — rumps.Window cria NSAlert e chama
        runModal(), que exigem isso (mesma regra do rumps.alert(), ver
        _set_state()).
        """
        resposta = rumps.Window(
            title=title,
            message=message,
            default_text=default_text,
            ok="Save",
            cancel="Cancel",
            dimensions=(340, 24),
        ).run()
        if not resposta.clicked:
            return None
        return resposta.text.strip()

    @rumps.clicked("Recent activity…")
    def open_activity(self, _):
        """As últimas linhas de "ouvi X / decidi Y", numa janela só.

        Existe pro teste de verdade no Mac: quando um comando não
        funciona, a pergunta é sempre "o que ele entendeu?" — e até
        agora a resposta já tinha sido sobrescrita pelo trecho
        seguinte, ou era uma notificação que sumiu em segundos.

        Roda a partir de um @rumps.clicked, ou seja, já na thread
        principal — que é o que rumps.alert() (NSAlert + runModal())
        exige. O texto transcrito vai como `message`, não como
        `title`: `message` é o argumento de informativeTextWithFormat:
        e o rumps dobra o "%" dele antes de passar adiante (conferido
        no source do rumps 0.4.0), então uma fala com "%" — "cinquenta
        por cento" vira "50%" com frequência — não vira código de
        formatação.
        """
        linhas = [_elide(l) for l in self._history]
        if not linhas:
            rumps.alert(
                "Recent activity",
                "Nothing yet. Start listening and say something.",
            )
            return
        rumps.alert("Recent activity", "\n".join(linhas))

    @rumps.clicked("Wake word…")
    def open_wake_word(self, _):
        nova = self._ask(
            "vIsper wake word",
            (
                "The word that wakes vIsper up. Everything you say after it "
                "is treated as a command.\n\n"
                "Pick a REAL, distinctive word — vIsper recognises it from a "
                "transcript, and made-up words get transcribed wrong. "
                "'Vesper', 'Iris' and 'Whisper' land far more reliably than "
                "an invented one.\n\n"
                "Leave it unchanged and press Save to keep what you have."
            ),
            config.WAKE_WORD,
        )
        if not nova or nova == config.WAKE_WORD:
            return
        if not save_settings({"WAKE_WORD": nova}):
            rumps.alert(f"Could not write the settings file:\n{settings_path()}")
            return
        rumps.alert(
            f"Wake word saved as “{nova}”. Quit and reopen vIsper to start "
            "using it — and update it on your iPhone too, or what it sends "
            "will be ignored."
        )

    @rumps.clicked("Spoken languages…")
    def open_languages(self, _):
        atual = ", ".join(config.TRANSCRIPTION_LANGUAGES) or "auto"
        resposta = self._ask(
            "Languages you speak",
            (
                "Comma-separated language codes — vIsper will never "
                "transcribe in anything outside this list.\n\n"
                "This is what fixes “it only understands English”: guessing "
                "the language from a few seconds of speech is unreliable, "
                "and whatever it guesses is the language it writes in — so a "
                "wrong guess becomes wrong TEXT.\n\n"
                "pt        one language only: skips the guess entirely\n"
                "pt, en    switches between them safely\n"
                "auto      no restriction (you take the guessing with it)"
            ),
            atual,
        )
        if resposta is None or not resposta:
            return
        if resposta.lower() in ("auto", "none"):
            novas = []
        else:
            novas = [p.strip().lower() for p in resposta.split(",") if p.strip()]
        if novas == list(config.TRANSCRIPTION_LANGUAGES):
            return
        if not save_settings({"TRANSCRIPTION_LANGUAGES": novas}):
            rumps.alert(f"Could not write the settings file:\n{settings_path()}")
            return

        # Vale JÁ, sem reiniciar: ao contrário da wake word (que outros
        # módulos leem uma vez, na importação), o idioma é lido a cada
        # transcrição a partir destes atributos. Fazer valer só depois
        # de reabrir seria pedir pra pessoa reiniciar o app pra testar
        # cada tentativa — justo no ajuste que ela mais vai querer
        # tentar de novo.
        config.TRANSCRIPTION_LANGUAGES = novas
        self._apply_languages(novas)
        rumps.alert(
            "Languages saved: "
            + (", ".join(novas) if novas else "auto (no restriction)")
            + ". It already applies — no need to restart."
        )

    @rumps.clicked("iPhone connection…")
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
        # As duas metades da história ficam no histórico: o que ele
        # OUVIU (via _set_heard) e o que ele DECIDIU fazer com isso.
        # Separadas, porque a falha mais comum é justamente as duas não
        # combinarem — ouviu certo e decidiu errado, ou nem ouviu.
        self._log_activity("→", resultado)
        notify("vIsper", "Status", resultado)
        # A máquina de estados é a fonte da verdade: depois de mandar,
        # a sessão volta pra ociosa, e o ícone tem que acompanhar. O
        # estado "sent" (posto por _on_dictation_send) fica até a
        # próxima transição — comparado via self._current_state, NÃO
        # self.icon: a troca de ícone é assíncrona (ver _set_state()),
        # então ler self.icon aqui logo em seguida podia pegar o valor
        # ANTIGO e reabrir a corrida que esse guard existe pra evitar.
        if self.session.dictating:
            self._set_state("dictating")
        elif self.listening and self._current_state != "sent":
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
            # rumps.alert() cria um NSAlert e chama runModal() — outra
            # chamada de AppKit que só pode acontecer na thread
            # principal, e este except roda dentro da thread de escuta
            # (_listen_loop_safe é o alvo de threading.Thread em
            # start_listening()). Mesmo despacho de _set_state(); ver
            # o comentário lá pro porquê.
            AppHelper.callAfter(
                rumps.alert,
                "vIsper needs Accessibility permission to type into your AI "
                "chat.\n\n"
                "Open System Settings › Privacy & Security › Accessibility "
                "and turn vIsper on, then start listening again.\n\n"
                f"({exc})",
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

    def _transcribe(self, chunk, language):
        """
        Uma passada de transcrição. Devolve (texto, info).

        `language=None` deixa o Whisper detectar; um código força.
        """
        segments, info = self.model.transcribe(
            chunk,
            language=language,
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
            # hotwords: o vocabulário de comando (wake word, nomes
            # das IAs, câmbio/over) entra como prioridade na
            # decodificação — "vIsper" é palavra inventada e, sem
            # isso, o Whisper escreve "whisper"/"vesper" com
            # frequência. Parâmetro conferido no fonte da wheel
            # faster-whisper==1.0.3 (a versão pinada), não de
            # memória. Cada chunk é uma chamada nova de
            # transcribe(), então a dica vale pra TODO chunk — não
            # só pro primeiro, como seria com initial_prompt em
            # áudio longo.
            hotwords=self._hotwords,
        )
        # Mesma correção de audio_file_input.py: os segmentos já
        # vêm com espaço embutido, " ".join() duplicava.
        texto = re.sub(r"\s+", " ", "".join(seg.text for seg in segments)).strip()
        return texto, info

    def _transcribe_in_my_languages(self, chunk):
        """
        Transcreve respeitando config.TRANSCRIPTION_LANGUAGES.

        Devolve (texto, rótulo_de_idioma) — o rótulo vai pro "Heard:".

        O problema real que isto resolve: detecção de idioma em áudio
        CURTO (nossos trechos são de ~4s) é conhecidamente pouco
        confiável, e o Whisper transcreve NO idioma que ele achou. Ou
        seja, detecção errada não produz só um rótulo errado — produz
        TEXTO errado. Foi o que apareceu como "só funciona em inglês".

        Três caminhos, por tamanho da lista:
          - 1 idioma  -> força, nem detecta. Mais rápido e sem chute.
          - vários    -> detecta, mas só aceita se cair na lista COM
                         confiança; senão refaz no idioma de reserva.
          - vazia     -> sem restrição, aceita o que vier.
        """
        if self._forced_language:
            texto, _info = self._transcribe(chunk, self._forced_language)
            return texto, self._forced_language

        texto, info = self._transcribe(chunk, None)

        if not self._allowed_languages:
            return texto, info.language  # sem restrição

        confiavel = info.language_probability >= config.LANGUAGE_CONFIDENCE_THRESHOLD
        if info.language in self._allowed_languages and confiavel:
            self._last_good_language = info.language
            return texto, info.language

        # Detecção fora da lista (ela não fala esse idioma) ou insegura
        # demais: refazer no idioma de reserva custa uma transcrição
        # extra, mas o texto da primeira passada estaria no idioma
        # errado de qualquer forma — não é desperdício, é a correção.
        reserva = self._last_good_language or self._allowed_languages[0]
        texto, _info = self._transcribe(chunk, reserva)
        # O rótulo mostra os DOIS: o que ele achou e o que a gente usou
        # no lugar. Sem isso, "refez em pt" e "detectou pt de primeira"
        # ficam indistinguíveis no "Heard:", e some a pista de que a
        # detecção está indo mal.
        return texto, f"{info.language}→{reserva}"

    def _listen_loop_whisper(self, stream):
        for chunk in stream.chunks():
            if not self.listening:
                break
            texto, rotulo_idioma = self._transcribe_in_my_languages(chunk)
            if texto:
                # O idioma entra junto no "Heard:" — diagnóstico direto
                # pra "ele não entende português": se aparecer "[en]"
                # com você falando português, o problema é a detecção
                # de idioma (ver config.TRANSCRIPTION_LANGUAGES), não o
                # app "não suportar" o idioma.
                self._set_heard(f"[{rotulo_idioma}] {texto}")
            self._on_result(self.session.handle(texto))

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
                # Só o idioma FORÇADO (lista de um item) chega aqui.
                # Com vários idiomas isso fica None e o Porcupine cai
                # na detecção crua — aceitável porque neste caminho o
                # áudio já vem recortado pela detecção acústica (é uma
                # fala inteira, não um trecho de 4s cego), que é
                # justamente a condição em que a detecção de idioma do
                # Whisper funciona bem. A validação de
                # _transcribe_in_my_languages() não se aplica aqui: o
                # PorcupineSession tem o próprio ciclo de transcrição.
                language=self._forced_language,
            )
            ps.run(gated_frames(), on_result=self._on_result)
        finally:
            self.porcupine_detector.stop()


if __name__ == "__main__":
    VisperApp().run()

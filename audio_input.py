"""
audio_input.py — lista e seleciona o microfone de entrada, e transmite
o áudio bruto capturado.

Dois jeitos de entrada já reconhecidos automaticamente, via
config.PREFERRED_INPUT_DEVICES (edite lá pra adicionar o seu, sem
mexer neste arquivo):
  - O receiver do DJI Mic (Mini ou outro): não precisa do app da DJI
    pra funcionar aqui, só plugar via USB-C que o macOS já lista ele
    como dispositivo de entrada normal (geralmente com nome "Wireless
    Microphone RX" ou contendo "DJI"). O app da DJI (Mimo / DJI Mic)
    só é necessário pra ajustar ganho e monitorar áudio no próprio
    mic — não pra esse programa conseguir ler o som dele.
  - Fones Bluetooth (ex.: Sony WH-1000XM5/WF-1000XM5): o macOS lista o
    fone pareado como dispositivo de entrada normal também, sem
    instalar nada — basta estar conectado. IMPORTANTE: usar o mic de
    um fone Bluetooth faz o Mac trocar o perfil dele pra HFP/HSP (o
    mesmo de ligação telefônica), o que derruba a qualidade do ÁUDIO
    DO SISTEMA INTEIRO pra mono enquanto o stream de entrada estiver
    aberto — não é bug daqui, é como o Bluetooth clássico funciona.
    Ver aviso completo no README.
"""

import json
from pathlib import Path

import sounddevice as sd
import numpy as np

import config

# Onde a escolha MANUAL de microfone (feita no submenu "Escolher
# microfone") é lembrada entre execuções do app — local padrão do
# macOS pra esse tipo de estado pequeno de app (não é config pra
# editar à mão, por isso não fica ao lado de config.py).
DEVICE_STATE_PATH = Path.home() / "Library" / "Application Support" / "vIsper" / "device.json"


def load_saved_device_name():
    """
    Lê o nome do dispositivo escolhido manualmente da última vez (ver
    save_device_choice()). Retorna None se nunca foi salvo, o arquivo
    não existe, ou está corrompido/ilegível — nesses casos main.py
    volta pro modo automático, o mesmo que já acontecia antes dessa
    função existir.

    Só o NOME é persistido, nunca um índice: índice de sounddevice não
    é um identificador estável nem DENTRO da mesma execução (ver
    resolve_device_by_name()), muito menos entre uma execução e outra.
    """
    try:
        data = json.loads(DEVICE_STATE_PATH.read_text())
    except (OSError, ValueError):
        return None
    name = data.get("device_name")
    return name if isinstance(name, str) and name else None


def save_device_choice(name):
    """
    Salva a escolha manual de microfone pra lembrar na próxima
    execução — chamado quando a pessoa escolhe um dispositivo no
    submenu. Chame com `name=None` pra ESQUECER a escolha salva (ao
    voltar pra "Detectar automaticamente"), senão a próxima execução
    ressuscitaria a escolha manual antiga em vez de respeitar a volta
    pro automático.

    Falha ao salvar (disco cheio, sem permissão de escrita etc.) é
    ignorada de propósito — isso é só conveniência entre execuções,
    nunca deve impedir a escolha de funcionar NESTA sessão.
    """
    try:
        DEVICE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEVICE_STATE_PATH.write_text(json.dumps({"device_name": name}))
    except OSError:
        pass


def list_input_devices():
    """Retorna uma lista de (índice, nome) de todo dispositivo de entrada disponível."""
    devices = sd.query_devices()
    return [
        (i, d["name"])
        for i, d in enumerate(devices)
        if d["max_input_channels"] > 0
    ]


def label_devices(devices):
    """
    Recebe uma lista [(índice, nome), ...] — mesmo formato de
    list_input_devices() — e devolve [(índice, nome, rótulo), ...].

    `rótulo` é igual a `nome`, EXCETO quando dois (ou mais)
    dispositivos da lista têm o nome exatamente igual: nesse caso o
    índice é anexado no rótulo (ex.: "WH-1000XM5 (índice 3)") pra
    desambiguar.

    Existe especificamente pro submenu "Escolher microfone" de
    main.py: rumps indexa os itens de um submenu pelo TÍTULO
    (Menu.add() só insere se o título ainda não existir) — sem isso,
    dois dispositivos com o mesmo nome fariam o segundo simplesmente
    SUMIR do menu, sem erro nenhum, impossível de selecionar.

    Importante: só o RÓTULO é desambiguado, pra exibição. Seleção e
    persistência (ver resolve_device_by_name()/save_device_choice())
    continuam usando `nome` puro — no caso raro de dois dispositivos
    IDÊNTICOS (mesmo nome de verdade, não só mesmo rótulo), escolher
    "um dos dois" no menu e escolher "o outro" resolvem pro mesmo nome
    salvo. Distinguir os dois de verdade exigiria persistir mais que o
    nome, o que não vale a complexidade pra um cenário tão raro.
    """
    name_counts = {}
    for _index, name in devices:
        name_counts[name] = name_counts.get(name, 0) + 1
    return [
        (
            index,
            name,
            f"{name} (índice {index})" if name_counts[name] > 1 else name,
        )
        for index, name in devices
    ]


def guess_preferred_device(preferred=None):
    """
    Tenta detectar automaticamente um dispositivo de entrada preferido,
    seguindo a ordem de prioridade de config.PREFERRED_INPUT_DEVICES
    (lista de grupos {"keywords": [...], "bluetooth": bool}).

    Percorre os GRUPOS em ordem; dentro de cada grupo, percorre os
    dispositivos conectados na ordem que o sistema operacional listou
    (list_input_devices()) e casa por SUBSTRING simples (sem acento
    nem palavra inteira — nome de hardware não é fala, não precisa da
    lógica de text_utils.py). O primeiro grupo que bater com qualquer
    dispositivo conectado ganha — ver config.py pro raciocínio de
    ordenar DJI antes do fone Bluetooth.

    `preferred`: normalmente omitido (usa config.PREFERRED_INPUT_DEVICES);
    dá pra passar uma lista própria, principalmente útil em teste.

    Retorna (índice, nome, is_bluetooth) do primeiro dispositivo que
    bateu, ou None se nada bateu com nenhum grupo.
    """
    if preferred is None:
        preferred = config.PREFERRED_INPUT_DEVICES
    devices = list_input_devices()
    for group in preferred:
        for index, name in devices:
            lowered = name.lower()
            if any(keyword in lowered for keyword in group["keywords"]):
                return index, name, group.get("bluetooth", False)
    return None


def resolve_device_by_name(name):
    """
    Resolve o índice ATUAL de um dispositivo de entrada pelo NOME
    exato. Usado quando uma escolha MANUAL foi feita antes — o índice
    do sounddevice/PortAudio é posicional, não um identificador
    estável: desconectar QUALQUER outro dispositivo pode reindexar
    todo mundo (ex.: o fone Bluetooth era índice 2, o DJI desconecta,
    o fone vira índice 1). Confiar num índice guardado de uma escolha
    manual antiga arriscaria abrir o stream de um dispositivo
    DIFERENTE do escolhido, em silêncio.

    Retorna o índice, ou None se nenhum dispositivo com esse nome
    estiver conectado agora (ex.: desconectou, ou o nome mudou).
    """
    for index, device_name in list_input_devices():
        if device_name == name:
            return index
    return None


def classify_device(name, preferred=None):
    """
    Dado o NOME de um dispositivo (ex.: escolhido manualmente no menu,
    não pela auto-detecção), diz se ele bate com algum grupo Bluetooth
    de config.PREFERRED_INPUT_DEVICES. Usado por main.py pra decidir
    se mostra o aviso de qualidade — mesma lógica de casamento de
    guess_preferred_device(), só que a partir de um nome já em mãos em
    vez de escanear os dispositivos de novo.

    Retorna True/False. Um nome que não bate com NENHUM grupo
    conhecido (ex.: mic embutido do Mac, ou outro dispositivo qualquer
    escolhido manualmente) retorna False — só avisamos quando temos
    certeza de que é Bluetooth, não por padrão.
    """
    if preferred is None:
        preferred = config.PREFERRED_INPUT_DEVICES
    lowered = name.lower()
    for group in preferred:
        if any(keyword in lowered for keyword in group["keywords"]):
            return group.get("bluetooth", False)
    return False


class AudioStream:
    """
    Envolve o InputStream do sounddevice pra entregar pedaços (chunks)
    de tamanho fixo de áudio, prontos pra detecção de wake-word ou
    transcrição.
    """

    def __init__(self, device_index, samplerate=16000, chunk_seconds=4, channels=1):
        self.device_index = device_index
        self.samplerate = samplerate
        self.chunk_seconds = chunk_seconds
        self.channels = channels

    def chunks(self):
        """
        Generator que entrega arrays numpy float32, cada um com
        `chunk_seconds` de duração, capturados do dispositivo escolhido.
        """
        blocksize = int(self.samplerate * self.chunk_seconds)
        with sd.InputStream(
            device=self.device_index,
            samplerate=self.samplerate,
            channels=self.channels,
            dtype="float32",
            blocksize=blocksize,
        ) as stream:
            while True:
                data, _overflowed = stream.read(blocksize)
                yield np.squeeze(data)

    def raw_frames(self, frame_length, dtype="int16"):
        """
        Generator que entrega frames pequenos de tamanho FIXO
        (`frame_length` amostras), no dtype pedido. Separado de
        chunks() de propósito: o Porcupine exige frames pequenos
        (~32ms) e int16, enquanto o Whisper trabalha melhor com
        blocos de segundos em float32 — são necessidades diferentes
        demais pra forçar no mesmo método.
        """
        with sd.InputStream(
            device=self.device_index,
            samplerate=self.samplerate,
            channels=self.channels,
            dtype=dtype,
            blocksize=frame_length,
        ) as stream:
            while True:
                data, _overflowed = stream.read(frame_length)
                yield np.squeeze(data)

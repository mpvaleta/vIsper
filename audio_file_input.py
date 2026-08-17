"""
audio_file_input.py — transcreve um arquivo de áudio já gravado (nota
de voz do WhatsApp, gravação solta, etc.) e processa o resultado pelo
MESMO pipeline do mic ao vivo e do relay do iPhone: passa pro
DictationSession.handle() compartilhado. Reaproveita o WhisperModel
já carregado por main.py — não recarrega o modelo.

Cobre o "upload de áudio" que ficou pendente no README: em vez de
inventar um jeito de mandar áudio bruto pra alguma IA (nenhuma aceita
isso direto — já checamos), transcreve local e deixa o texto seguir
o fluxo normal (abre IA e/ou vira parte do ditado, dependendo do que
o texto disser, exatamente como aconteceria se você tivesse falado
aquilo no mic).
"""

import re
import time
from pathlib import Path

SUPPORTED_EXTENSIONS = {".m4a", ".mp3", ".wav", ".ogg", ".opus", ".aac"}


def is_supported_audio_file(path) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_EXTENSIONS


def transcribe_and_handle(path, model, session, language=None):
    """
    path: caminho do arquivo de áudio.
    model: instância de faster_whisper.WhisperModel já carregada (a
           mesma que main.py usa pro mic).
    session: DictationSession compartilhada com mic/relay, pra manter
             um único estado de "tô ditando ou não" entre as três
             fontes de entrada.
    Retorna o que DictationSession.handle() retornar (pra
    notificação), ou uma mensagem de erro se o arquivo não existir ou
    não for um formato suportado.
    """
    path = Path(path)
    if not path.exists():
        return f"arquivo não encontrado: {path}"
    if not is_supported_audio_file(path):
        return f"formato não suportado: {path.suffix}"

    segments, _info = model.transcribe(str(path), language=language)
    # Os segmentos do faster-whisper já vêm com o espaço embutido no
    # início de cada um (característica do tokenizer) — juntar com
    # " ".join() duplicava o espaço entre eles. Concatena direto e
    # normaliza qualquer espaço sobrando.
    text = re.sub(r"\s+", " ", "".join(seg.text for seg in segments)).strip()
    return session.handle(text)


def watch_folder(folder, model, session, language=None, on_result=None, poll_seconds=3):
    """
    Fica de olho numa pasta (ex.: onde você arrasta um áudio
    exportado do WhatsApp). Cada arquivo novo suportado é transcrito
    e processado uma vez só — o arquivo em si NÃO é apagado do disco,
    só marcado como já visto (em memória, então reinicia o app e ele
    esquece o que já processou).

    De propósito simples (polling, não FSEvents nativo do macOS) —
    dá pra trocar por um watcher de verdade depois, se o polling
    incomodar. Roda pra sempre — chamar isso numa thread própria,
    como o resto do app já faz com o mic e o relay.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    seen = set()

    while True:
        for f in sorted(folder.iterdir()):
            if f.is_file() and is_supported_audio_file(f) and f not in seen:
                seen.add(f)
                result = transcribe_and_handle(f, model, session, language=language)
                if on_result:
                    on_result(result)
        time.sleep(poll_seconds)

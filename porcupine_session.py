"""
porcupine_session.py — usa o Porcupine pra detectar a wake word (o
SOM dela, não uma transcrição) tanto pra abrir quanto pra fechar o
ditado, sem manter dois motores pesados (Porcupine + Whisper
contínuo) rodando ao mesmo tempo o tempo todo — foi essa concorrência
que segurou a integração na rodada anterior.

Ideia central: o Porcupine só sabe dizer "a wake word foi dita agora"
— não sabe o que mais foi falado. Então:

  - Enquanto OCIOSO: só o Porcupine roda (barato, frames pequenos).
    Ao detectar, grava alguns segundos de áudio BRUTO (sem
    transcrever ainda) pra pegar o nome da IA que vem a seguir, e aí
    sim transcreve só esse trecho curto com Whisper.

  - Enquanto DITANDO: em vez de manter o Whisper transcrevendo o
    tempo todo (como a v1 faz), só ACUMULA o áudio bruto num buffer
    (isso é barato — não é transcrição) enquanto o Porcupine escuta a
    wake word de fechamento a cada frame, no mesmo loop. Ao detectar,
    transcreve o buffer inteiro de uma vez só e manda pro
    DictationSession. Existe também um teto de segurança
    (max_dictation_seconds) que força o fechamento se a wake word de
    fechamento nunca vier — pra não crescer o buffer pra sempre.

Isso mantém o ganho principal do Porcupine (bem menos falso
positivo/negativo do que procurar a wake word numa transcrição
contínua) sem precisar de threads/loops concorrentes de verdade —
tudo acontece num loop só, frame por frame.

Simplificação conhecida: durante os poucos segundos de captura do
nome da IA (logo após abrir), o Porcupine não processa esses frames
— então, se a wake word for dita de novo bem nesse instante, não é
pega ali; só volta a valer no frame seguinte, quando o loop principal
retoma. Aceitável pro uso normal (ninguém fala a wake word duas vezes
seguidas rápido assim), mas vale saber que existe.

AINDA NÃO LIGADO a áudio real — ver PorcupineSession.run(), que
espera um frame_source (iterável de frames int16 do tamanho de
detector.frame_length) e um model (WhisperModel real ou compatível).
Testado com os dois simulados (test_porcupine_session.py) — o
comportamento com mic e motor Porcupine de verdade continua sem
validar, como todo o resto que depende de hardware real.
"""

import re

import numpy as np

from config import WAKE_WORD


class PorcupineSession:
    def __init__(
        self,
        detector,
        model,
        session,
        sample_rate,
        language=None,
        open_capture_seconds=3,
        max_dictation_seconds=120,
    ):
        """
        detector: PorcupineWakeWordDetector já iniciado (.start() já
                  chamado) — usa .frame_length e .process_frame().
        model: WhisperModel (ou qualquer objeto com .transcribe()
               compatível) — chamado só nos dois momentos em que
               texto de verdade é necessário: nome da IA, e conteúdo
               final do ditado.
        session: DictationSession — a MESMA instância compartilhada
                 com mic normal e relay do iPhone.
        """
        self.detector = detector
        self.model = model
        self.session = session
        self.sample_rate = sample_rate
        self.language = language
        self.open_capture_seconds = open_capture_seconds
        self.max_dictation_frames = max(
            1, int(max_dictation_seconds * sample_rate / detector.frame_length)
        )

    def _transcribe(self, frames):
        if not frames:
            return ""
        audio = np.concatenate(frames).astype(np.float32) / 32768.0
        segments, _info = self.model.transcribe(audio, language=self.language)
        # mesma correção de audio_file_input.py/main.py: não juntar
        # com espaço extra, os segmentos já vêm com ele embutido.
        text = "".join(seg.text for seg in segments)
        return re.sub(r"\s+", " ", text).strip()

    def run(self, frame_source, on_result=None):
        """
        frame_source: iterável (tipicamente um gerador sem fim) de
                      frames int16, cada um com exatamente
                      detector.frame_length amostras.
        on_result: função opcional(str) -> None, chamada com o que
                   DictationSession.handle() retornar — mesmo padrão
                   de relay_listener.py e do loop de mic em main.py.
        """
        frames_per_open_capture = max(
            1, int(self.open_capture_seconds * self.sample_rate / self.detector.frame_length)
        )
        dictation_buffer = []
        it = iter(frame_source)

        for frame in it:
            if not self.session.dictating:
                if not self.detector.process_frame(frame):
                    continue
                extra = []
                for _ in range(frames_per_open_capture):
                    try:
                        extra.append(next(it))
                    except StopIteration:
                        break
                text = self._transcribe(extra)
                result = self.session.handle(f"{WAKE_WORD} {text}".strip())
                if result and on_result:
                    on_result(result)
            else:
                dictation_buffer.append(frame)
                closed = self.detector.process_frame(frame)
                hit_cap = len(dictation_buffer) >= self.max_dictation_frames
                if closed or hit_cap:
                    text = self._transcribe(dictation_buffer)
                    dictation_buffer = []
                    # Duas chamadas de propósito, não uma combinada:
                    # DictationSession.handle() só sabe montar a
                    # mensagem final a partir do PRÓPRIO buffer
                    # interno dela (populado por chamadas sem a wake
                    # word), não do texto passado na chamada que
                    # fecha. Primeiro alimenta o conteúdo, depois
                    # fecha com a wake word sozinha — mesmo contrato
                    # que o loop de mic contínuo já usa hoje.
                    if text:
                        self.session.handle(text)
                    result = self.session.handle(WAKE_WORD)
                    if result and on_result:
                        on_result(result)

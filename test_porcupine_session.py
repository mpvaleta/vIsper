"""
Testa porcupine_session.py com o motor Porcupine e o WhisperModel
simulados (sem hardware real — mesma ressalva de
wake_word_porcupine.py). Cobre: abrir a IA certa a partir da captura
curta pós-detecção; acumular o áudio e transcrever o buffer inteiro
só UMA VEZ no fechamento (não chamada por chamada); o teto de
segurança por tempo máximo; e fechar sem quebrar quando não foi
ditado nada de verdade.
"""

import unittest

import numpy as np

from command_router import CommandRouter
from dictation import DictationSession
from porcupine_session import PorcupineSession


class FakeDetector:
    def __init__(self, script, frame_length=512):
        self.frame_length = frame_length
        self._script = list(script)
        self._i = 0

    def process_frame(self, frame):
        if self._i >= len(self._script):
            return False
        result = self._script[self._i]
        self._i += 1
        return result


class FakeSegment:
    def __init__(self, text):
        self.text = text


class FakeModel:
    def __init__(self, responses):
        self._responses = list(responses)  # uma resposta por chamada
        self.calls = []

    def transcribe(self, audio, language=None):
        self.calls.append(audio)
        text = self._responses.pop(0) if self._responses else ""
        return [FakeSegment(text)], None


def _frame(frame_length=512):
    return np.zeros(frame_length, dtype=np.int16)


class PorcupineSessionTest(unittest.TestCase):
    def _build_session(self, calls):
        ai_actions = {"claude": lambda: calls.append("abriu_claude")}
        router = CommandRouter(ai_actions)
        return DictationSession(
            router=router,
            paste_action=lambda t: calls.append(("colou", t)),
            send_action=lambda: calls.append("mandou_enter"),
        )

    def test_abre_a_ia_certa_com_a_captura_curta(self):
        calls = []
        session = self._build_session(calls)
        detector = FakeDetector(script=[False, False, True])
        model = FakeModel(responses=["claude"])
        ps = PorcupineSession(
            detector, model, session, sample_rate=16000, open_capture_seconds=0.09
        )
        # 0.09s * 16000 / 512 frames ~= 2 frames de captura extra
        frames = [_frame() for _ in range(7)]

        ps.run(frames)

        self.assertIn("abriu_claude", calls)
        self.assertTrue(session.dictating)

    def test_fecha_com_o_buffer_inteiro_transcrito_de_uma_vez(self):
        calls = []
        session = self._build_session(calls)
        session.dictating = True  # já dentro de um ditado

        detector = FakeDetector(script=[False, False, False, False, True])
        model = FakeModel(responses=["confirma a reuniao de amanha"])
        ps = PorcupineSession(detector, model, session, sample_rate=16000)

        ps.run([_frame() for _ in range(5)])

        self.assertFalse(session.dictating)
        self.assertIn(("colou", "confirma a reuniao de amanha"), calls)
        self.assertIn("mandou_enter", calls)
        self.assertEqual(len(model.calls), 1, "deveria transcrever o buffer inteiro uma vez só, não por frame")

    def test_teto_de_seguranca_forca_o_fechamento(self):
        calls = []
        session = self._build_session(calls)
        session.dictating = True

        detector = FakeDetector(script=[False] * 10)  # nunca detecta o fechamento
        model = FakeModel(responses=["algo bem longo"])
        ps = PorcupineSession(
            detector, model, session, sample_rate=16000, max_dictation_seconds=0.16
        )
        # 0.16s * 16000 / 512 = 5 frames de teto
        ps.run([_frame() for _ in range(10)])

        self.assertFalse(session.dictating)
        self.assertIn("mandou_enter", calls)

    def test_wake_word_transcrita_junto_nao_reabre_a_ia_padrao(self):
        # Regressão séria, e o caso NORMAL, não o excepcional: o áudio
        # da wake word de fechamento está DENTRO do buffer de ditado (o
        # frame que dispara a detecção entra no buffer antes de ser
        # processado), então o Whisper transcreve ela junto com o
        # conteúdo. O fechamento era feito em DUAS chamadas —
        # handle(conteúdo) e depois handle(WAKE_WORD) — e a primeira já
        # fechava o ditado sozinha por causa dessa wake word embutida.
        # A segunda caía numa sessão OCIOSA, onde wake word sozinha
        # quer dizer "abre a IA padrão": cada envio abria uma aba nova
        # do Claude e deixava o app preso em modo ditado de novo.
        calls = []
        session = self._build_session(calls)
        session.dictating = True

        detector = FakeDetector(script=[False, False, False, False, True])
        model = FakeModel(responses=["confirma a reuniao de amanha vIsper"])
        ps = PorcupineSession(detector, model, session, sample_rate=16000)

        ps.run([_frame() for _ in range(5)])

        self.assertIn(("colou", "confirma a reuniao de amanha"), calls)
        self.assertIn("mandou_enter", calls)
        self.assertNotIn("abriu_claude", calls, "não podia ter aberto a IA de novo")
        self.assertFalse(session.dictating, "não podia ter voltado pro modo ditado")

    def test_gatilho_de_fechamento_falado_junto_tambem_nao_reabre(self):
        # Mesma armadilha com "over"/"câmbio" em vez da wake word: a
        # pessoa fala "...over" e o Porcupine fecha pelo som da wake
        # word logo depois (ou pelo teto de tempo).
        calls = []
        session = self._build_session(calls)
        session.dictating = True

        detector = FakeDetector(script=[False, False, True])
        model = FakeModel(responses=["algumas ideias pra amanha over"])
        ps = PorcupineSession(detector, model, session, sample_rate=16000)

        ps.run([_frame() for _ in range(3)])

        self.assertIn(("colou", "algumas ideias pra amanha"), calls)
        self.assertNotIn("abriu_claude", calls)
        self.assertFalse(session.dictating)

    def test_conteudo_vazio_fecha_sem_colar_nem_mandar(self):
        calls = []
        session = self._build_session(calls)
        session.dictating = True
        session.buffer = []

        detector = FakeDetector(script=[True])  # fecha já no 1º frame, sem conteúdo
        model = FakeModel(responses=[""])
        ps = PorcupineSession(detector, model, session, sample_rate=16000)

        ps.run([_frame()])

        self.assertFalse(session.dictating)
        self.assertNotIn("mandou_enter", calls)
        pasted = [c for c in calls if isinstance(c, tuple) and c[0] == "colou"]
        self.assertEqual(pasted, [])


if __name__ == "__main__":
    unittest.main()

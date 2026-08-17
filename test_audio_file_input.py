"""
Testa audio_file_input.py: formato suportado/não suportado, arquivo
inexistente, e que a transcrição vira uma chamada certa em
DictationSession.handle() (com WhisperModel simulado — não precisa
de um modelo de verdade nem de áudio de verdade pra testar essa
parte).
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import audio_file_input as afi


class FakeSegment:
    def __init__(self, text):
        self.text = text


class AudioFileInputTest(unittest.TestCase):
    def test_reconhece_formato_suportado(self):
        self.assertTrue(afi.is_supported_audio_file("nota.m4a"))
        self.assertTrue(afi.is_supported_audio_file("NOTA.MP3"))  # case-insensitive
        self.assertFalse(afi.is_supported_audio_file("nota.txt"))

    def test_arquivo_inexistente_nao_chama_o_modelo(self):
        model = MagicMock()
        session = MagicMock()

        result = afi.transcribe_and_handle(
            "/tmp/isso-de-certeza-nao-existe-aqui.m4a", model, session
        )

        self.assertIn("não encontrado", result)
        model.transcribe.assert_not_called()
        session.handle.assert_not_called()

    def test_transcreve_e_passa_pro_session(self):
        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as f:
            path = f.name
        try:
            model = MagicMock()
            model.transcribe.return_value = (
                [FakeSegment("vIsper claude"), FakeSegment(" confirma o teste")],
                None,
            )
            session = MagicMock()
            session.handle.return_value = "abriu claude — ouvindo ditado"

            result = afi.transcribe_and_handle(path, model, session)

            model.transcribe.assert_called_once_with(path, language=None)
            session.handle.assert_called_once_with("vIsper claude confirma o teste")
            self.assertEqual(result, "abriu claude — ouvindo ditado")
        finally:
            Path(path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()

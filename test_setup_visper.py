"""
Testa setup_visper.py — o assistente de primeira configuração.

Foco: a pergunta 3 (idiomas) tem que VALIDAR antes de aceitar, não só
depois — sem isso, um palpite natural de quem fala português ("pt-BR",
"português") era silenciosamente descartado por save_settings() (que
só confere a FORMA lá dentro) enquanto o script imprimia "Salvo:
TRANSCRIPTION_LANGUAGES", uma confirmação FALSA. main.py's menu pro
mesmo ajuste já validava assim; este arquivo não tinha o mesmo cuidado.

Aponta VISPER_SETTINGS_PATH pra um diretório temporário, nunca o
settings.json de verdade — mesmo padrão de test_user_settings.py.
"""

import json
import os
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import setup_visper
import user_settings


class SetupVisperTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "settings.json"
        self._anterior = os.environ.get(user_settings.ENV_OVERRIDE)
        os.environ[user_settings.ENV_OVERRIDE] = str(self.path)

    def tearDown(self):
        if self._anterior is None:
            os.environ.pop(user_settings.ENV_OVERRIDE, None)
        else:
            os.environ[user_settings.ENV_OVERRIDE] = self._anterior
        self._tmp.cleanup()

    def _rodar(self, respostas):
        """Roda main() com as respostas dadas, uma por input(). Devolve
        (código de saída, texto impresso). Nunca toca no clipboard nem
        na rede de verdade (pbcopy engolido por copiar(), ntfy nunca
        chamado — respostas incluem "n" pras perguntas de ntfy/
        porcupine, então novo_topico() nunca é sequer chamado)."""
        saida = StringIO()
        with patch("builtins.input", side_effect=respostas), patch(
            "sys.stdout", saida
        ):
            codigo = setup_visper.main()
        return codigo, saida.getvalue()

    def _lido(self):
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_codigo_invalido_e_recusado_e_pede_de_novo(self):
        # "pt-BR" é justamente o palpite que a documentação do projeto
        # cita como erro natural de quem fala português.
        codigo, saida = self._rodar(["", "", "pt-BR", "pt", "n", "n"])
        self.assertEqual(codigo, 0)
        self.assertIn("não é código de idioma", saida)
        self.assertEqual(self._lido().get("TRANSCRIPTION_LANGUAGES"), ["pt"])

    def test_nunca_grava_o_codigo_invalido_nem_de_passagem(self):
        # O padrão de config.py já é ["pt", "en"] — usa "pt, es" como
        # resposta válida final pra ter certeza de que é o QUE FOI
        # DIGITADO (não o padrão) que acaba gravado.
        codigo, _saida = self._rodar(["", "", "português", "pt, es", "n", "n"])
        self.assertEqual(codigo, 0)
        self.assertEqual(
            self._lido().get("TRANSCRIPTION_LANGUAGES"), ["pt", "es"]
        )

    def test_nao_imprime_salvo_com_confirmacao_falsa(self):
        # A falha real: mesmo com o código inválido, o script ANTES
        # disto imprimia "Salvo: TRANSCRIPTION_LANGUAGES" — verdade
        # sobre o arquivo ter sido escrito, mentira sobre o que tinha
        # dentro. Com a validação, o valor que chega em save_settings()
        # já é válido, então "Salvo" (quando aparecer) é sempre verdade.
        codigo, saida = self._rodar(["", "", "eng", "pt", "n", "n"])
        self.assertEqual(codigo, 0)
        linha_salvo = [l for l in saida.splitlines() if l.strip().startswith("Salvo")]
        self.assertTrue(linha_salvo)
        self.assertIn("TRANSCRIPTION_LANGUAGES", linha_salvo[0])
        self.assertEqual(self._lido().get("TRANSCRIPTION_LANGUAGES"), ["pt"])

    def test_auto_continua_aceito_sem_pedir_de_novo(self):
        codigo, saida = self._rodar(["", "", "auto", "n", "n"])
        self.assertEqual(codigo, 0)
        self.assertNotIn("não é código de idioma", saida)

    def test_varios_codigos_invalidos_de_uma_vez_sao_todos_listados(self):
        codigo, saida = self._rodar(["", "", "pt-BR, eng", "pt, en", "n", "n"])
        self.assertEqual(codigo, 0)
        self.assertIn("pt-BR", saida)
        self.assertIn("eng", saida)

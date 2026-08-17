"""
Testes de actions.py — mocka subprocess.run pra não depender de macOS
de verdade (open/osascript/pbcopy não existem neste sandbox Linux).

O que importa cobrir aqui não é "abre a URL certa" (isso é trivial e
já dava pra ver só lendo o código) — é que TODA chamada usa
check=True, e que uma falha de verdade (ex.: osascript recusando por
falta de permissão de Acessibilidade) VIRA uma exceção em vez de
desaparecer em silêncio. Antes dessa mudança, uma falha aqui não tinha
jeito nenhum de chegar até quem chamou.
"""

import subprocess
import unittest
from unittest.mock import call, patch

import actions


class OpenActionsTest(unittest.TestCase):
    @patch("actions.subprocess.run")
    def test_open_claude_usa_check_true(self, mock_run):
        actions.open_claude()
        mock_run.assert_called_once_with(["open", "https://claude.ai/new"], check=True)

    @patch("actions.subprocess.run")
    def test_open_chatgpt_usa_check_true(self, mock_run):
        actions.open_chatgpt()
        mock_run.assert_called_once_with(["open", "https://chat.openai.com/"], check=True)

    @patch("actions.subprocess.run")
    def test_open_claude_code_usa_osascript_com_check_true(self, mock_run):
        actions.open_claude_code()
        self.assertEqual(mock_run.call_count, 1)
        args, kwargs = mock_run.call_args
        self.assertEqual(args[0][0], "osascript")
        self.assertTrue(kwargs.get("check"))

    @patch("actions.subprocess.run")
    def test_falha_ao_abrir_propaga_em_vez_de_sumir(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, ["open"])
        with self.assertRaises(subprocess.CalledProcessError):
            actions.open_claude()


class PasteTextTest(unittest.TestCase):
    @patch("actions.subprocess.run")
    def test_copia_e_cola_nessa_ordem_com_check_true(self, mock_run):
        actions.paste_text("olá mundo")
        self.assertEqual(mock_run.call_count, 2)
        pbcopy_call, keystroke_call = mock_run.call_args_list
        self.assertEqual(pbcopy_call, call(["pbcopy"], input="olá mundo".encode("utf-8"), check=True))
        self.assertTrue(keystroke_call.kwargs.get("check"))
        self.assertIn("v", keystroke_call.args[0][-1])

    @patch("actions.subprocess.run")
    def test_falha_no_pbcopy_nao_tenta_colar(self, mock_run):
        # check=True faz o pbcopy falhar levantar ANTES da segunda
        # chamada (o Cmd+V) — sem isso, colaria um clipboard antigo/
        # errado sem avisar que o texto novo nunca chegou lá.
        mock_run.side_effect = subprocess.CalledProcessError(1, ["pbcopy"])
        with self.assertRaises(subprocess.CalledProcessError):
            actions.paste_text("qualquer coisa")
        self.assertEqual(mock_run.call_count, 1)


class HandleDoneTest(unittest.TestCase):
    @patch("actions.subprocess.run")
    def test_aperta_enter_com_check_true(self, mock_run):
        actions.handle_done()
        args, kwargs = mock_run.call_args
        self.assertEqual(args[0][0], "osascript")
        self.assertIn("return", args[0][-1])
        self.assertTrue(kwargs.get("check"))

    @patch("actions.subprocess.run")
    def test_falha_por_falta_de_permissao_propaga(self, mock_run):
        # Cenário real: Acessibilidade não concedida ainda — antes
        # dessa mudança, isso não fazia nada e não avisava ninguém.
        mock_run.side_effect = subprocess.CalledProcessError(1, ["osascript"])
        with self.assertRaises(subprocess.CalledProcessError):
            actions.handle_done()


class PlaySoundTest(unittest.TestCase):
    @patch("actions.subprocess.Popen")
    def test_toca_afplay_com_o_som_certo_sem_esperar(self, mock_popen):
        actions.play_sound("Pop")
        mock_popen.assert_called_once_with(
            ["afplay", "/System/Library/Sounds/Pop.aiff"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @patch("actions.subprocess.Popen")
    def test_nome_vazio_nao_chama_afplay(self, mock_popen):
        actions.play_sound("")
        mock_popen.assert_not_called()

    @patch("actions.subprocess.Popen")
    def test_falha_ao_tocar_nao_propaga(self, mock_popen):
        # Diferente de paste_text/handle_done: som é só estética, uma
        # falha aqui (ex.: afplay não encontrado) não pode derrubar o
        # fluxo de ditado nem fingir que a ação real falhou.
        mock_popen.side_effect = OSError("afplay não encontrado")
        try:
            actions.play_sound("Pop")
        except OSError:
            self.fail("play_sound() não devia propagar OSError")


class AiActionsTest(unittest.TestCase):
    def test_toda_acao_e_chamavel_sem_argumento(self):
        # AI_ACTIONS é chamado como router.route()/DictationSession
        # chamam: self.ai_actions[nome]() — sem argumento nenhum.
        with patch("actions.subprocess.run"):
            for name, action in actions.AI_ACTIONS.items():
                with self.subTest(ai=name):
                    action()  # não deve levantar TypeError de assinatura


if __name__ == "__main__":
    unittest.main()

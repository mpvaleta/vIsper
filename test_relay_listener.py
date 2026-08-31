"""
Testa relay_listener.py com a rede simulada (sem sandbox com acesso
ao ntfy.sh real). Cobre: eventos "message" viram chamadas em
DictationSession.handle(); eventos "open"/keepalive e linhas vazias
são ignorados; o loop para quando .running vira False.

Isso NÃO substitui testar contra o ntfy.sh de verdade — só garante
que a lógica de parsing e a integração com DictationSession estão
corretas antes desse teste real.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

import requests

from command_router import CommandRouter
from dictation import DictationSession
from relay_listener import RelayListener


class FakeResponse:
    """Imita o objeto de resposta streaming do requests.get, incluindo
    o protocolo de context manager (with ... as resp)."""

    def __init__(self, lines, on_exhausted=None):
        self._lines = lines
        self._on_exhausted = on_exhausted

    def raise_for_status(self):
        pass

    def iter_lines(self):
        for line in self._lines:
            yield line
        if self._on_exhausted:
            self._on_exhausted()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class RelayListenerTest(unittest.TestCase):
    def _build_session(self, calls):
        ai_actions = {"claude": lambda: calls.append("abriu_claude")}
        router = CommandRouter(ai_actions)
        return DictationSession(
            router=router,
            paste_action=lambda t: calls.append(("colou", t)),
            send_action=lambda: calls.append("mandou_enter"),
        )

    def test_processa_mensagem_e_ignora_o_resto(self):
        calls = []
        session = self._build_session(calls)
        listener = RelayListener(session, topic="teste-topico-bem-aleatorio")

        lines = [
            b'{"event": "open"}',  # keepalive de conexão, ignora
            b"",  # linha vazia (heartbeat), ignora
            json.dumps({"event": "message", "message": "vIsper claude"}).encode(),
            json.dumps(
                {"event": "message", "message": "confirma a reuniao de amanha"}
            ).encode(),
            json.dumps({"event": "message", "message": "vIsper pronto"}).encode(),
        ]

        def fake_get(*args, **kwargs):
            return FakeResponse(
                lines, on_exhausted=lambda: setattr(listener, "running", False)
            )

        results = []
        with patch("relay_listener.requests.get", side_effect=fake_get):
            listener.listen_forever(on_result=results.append)

        self.assertIn("abriu_claude", calls)
        self.assertIn(("colou", "confirma a reuniao de amanha"), calls)
        self.assertIn("mandou_enter", calls)
        self.assertTrue(any("opened claude" in r for r in results))
        self.assertTrue(any(r.startswith("sent:") for r in results))

    def test_json_invalido_nao_derruba_a_thread(self):
        calls = []
        session = self._build_session(calls)
        listener = RelayListener(session, topic="outro-topico-aleatorio")

        # uma linha de JSON quebrado seguida de uma mensagem válida —
        # a linha quebrada não pode impedir a válida de ser processada
        call_count = {"n": 0}

        def fake_get(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return FakeResponse([b"{isso nao e json valido"])
            return FakeResponse(
                [json.dumps({"event": "message", "message": "vIsper claude"}).encode()],
                on_exhausted=lambda: setattr(listener, "running", False),
            )

        with patch("relay_listener.requests.get", side_effect=fake_get), patch(
            "relay_listener.time.sleep"
        ):
            listener.listen_forever()

        self.assertIn("abriu_claude", calls)

    def test_backoff_cresce_e_reseta_depois_de_reconectar(self):
        calls = []
        session = self._build_session(calls)
        listener = RelayListener(session, topic="mais-um-topico-aleatorio")
        sleep_calls = []
        attempt = {"n": 0}

        def fake_get(*args, **kwargs):
            attempt["n"] += 1
            if attempt["n"] in (1, 2, 3):
                raise requests.RequestException("falha simulada")
            if attempt["n"] == 4:
                return FakeResponse([])  # reconecta, sem mensagem nenhuma
            if attempt["n"] == 5:
                raise requests.RequestException("falha de novo, já tinha reconectado")
            listener.running = False
            return FakeResponse([])

        with patch("relay_listener.requests.get", side_effect=fake_get), patch(
            "relay_listener.time.sleep", side_effect=sleep_calls.append
        ):
            listener.listen_forever()

        # 3 falhas seguidas dobram (5, 10, 20); a 4ª conecta de verdade
        # e reseta pra 5 — e espera esses 5s antes de reconectar, mesmo
        # tendo terminado limpa (era o bug: stream que acaba SEM
        # exceção reconectava na hora, sem pausa nenhuma). A falha
        # seguinte (5ª) continua de onde o backoff parou, 10s.
        self.assertEqual(sleep_calls, [5, 10, 20, 5, 10])

    def test_stream_que_termina_limpo_nao_reconecta_em_laco_sem_pausa(self):
        # Regressão: quando o ntfy fecha o stream sem erro (servidor
        # reiniciou, proxy derrubou por ociosidade), iter_lines()
        # simplesmente acaba e nenhuma exceção é levantada. Antes, esse
        # caminho não passava por time.sleep() nenhum e o `while`
        # reabria a conexão na hora — um servidor que aceitasse e
        # fechasse na sequência virava um laço de requisições HTTPS a
        # toda velocidade contra o ntfy.sh.
        calls = []
        session = self._build_session(calls)
        listener = RelayListener(session, topic="topico-que-fecha-limpo")
        sleep_calls = []
        attempt = {"n": 0}

        def fake_get(*args, **kwargs):
            attempt["n"] += 1
            if attempt["n"] >= 4:
                listener.running = False
            return FakeResponse([])  # conecta e fecha limpo, sem exceção

        with patch("relay_listener.requests.get", side_effect=fake_get), patch(
            "relay_listener.time.sleep", side_effect=sleep_calls.append
        ):
            listener.listen_forever()

        self.assertEqual(
            len(sleep_calls),
            3,
            "toda reconexão precisa esperar, não só as que falharam com exceção",
        )
        self.assertTrue(all(s > 0 for s in sleep_calls))

    def test_nao_espera_depois_de_stop(self):
        # stop() no meio do stream não pode custar mais um backoff
        # inteiro antes da thread sair.
        calls = []
        session = self._build_session(calls)
        listener = RelayListener(session, topic="topico-que-para-no-meio")
        sleep_calls = []

        def fake_get(*args, **kwargs):
            return FakeResponse([], on_exhausted=listener.stop)

        with patch("relay_listener.requests.get", side_effect=fake_get), patch(
            "relay_listener.time.sleep", side_effect=sleep_calls.append
        ):
            listener.listen_forever()

        self.assertEqual(sleep_calls, [])


if __name__ == "__main__":
    unittest.main()


class TravasDoRelayTest(unittest.TestCase):
    """
    O tópico do ntfy é a única senha do canal. Estas travas são a
    SEGUNDA, pro caso da primeira falhar — ver config.RELAY_BLOCKED_AIS
    e RELAY_MAX_MESSAGE_CHARS.
    """

    def _session(self, dictating=False, preview_ai=None):
        session = MagicMock()
        session.dictating = dictating
        session.router.preview.return_value = preview_ai
        session.handle_complete.return_value = "ok"
        return session

    def test_claude_code_pelo_iphone_e_recusado(self):
        # Abrir o Terminal e digitar nele é execução de comando, não
        # "digitar num chat de IA" — a diferença de gravidade entre as
        # duas é grande demais pra deixar no mesmo balde.
        session = self._session(preview_ai="claude_code")
        listener = RelayListener(session, topic="t", blocked_ais=["claude_code"])

        resultado = listener._handle_message("vIsper claude code rm -rf algo over")

        session.handle_complete.assert_not_called()
        self.assertIn("claude_code", resultado)

    def test_recusa_explica_em_vez_de_sumir_calada(self):
        # Mensagem sumindo sem explicação é indistinguível de "o relay
        # não está funcionando".
        session = self._session(preview_ai="claude_code")
        listener = RelayListener(session, topic="t", blocked_ais=["claude_code"])
        self.assertTrue(listener._handle_message("vIsper claude code oi"))

    def test_ia_permitida_passa_normalmente(self):
        session = self._session(preview_ai="claude")
        listener = RelayListener(session, topic="t", blocked_ais=["claude_code"])

        resultado = listener._handle_message("vIsper claude qual é a previsão over")

        session.handle_complete.assert_called_once_with(
            "vIsper claude qual é a previsão over"
        )
        self.assertEqual(resultado, "ok")

    def test_com_ditado_ja_aberto_nao_consulta_o_roteador(self):
        # Texto durante o ditado é CONTEÚDO, não passa pelo roteador —
        # consultar preview() aqui poderia barrar uma frase legítima só
        # por ela conter as palavras "claude code".
        session = self._session(dictating=True, preview_ai="claude_code")
        listener = RelayListener(session, topic="t", blocked_ais=["claude_code"])

        listener._handle_message("preciso revisar o claude code amanhã")

        session.router.preview.assert_not_called()
        session.handle_complete.assert_called_once()

    def test_lista_de_bloqueio_vazia_libera_tudo(self):
        session = self._session(preview_ai="claude_code")
        listener = RelayListener(session, topic="t", blocked_ais=[])
        listener._handle_message("vIsper claude code oi")
        session.handle_complete.assert_called_once()

    def test_mensagem_gigante_e_cortada_antes_de_ser_colada(self):
        session = self._session(preview_ai="claude")
        listener = RelayListener(session, topic="t", max_chars=50)

        resultado = listener._handle_message("x" * 51)

        session.handle_complete.assert_not_called()
        self.assertIn("grande demais", resultado)

    def test_mensagem_no_limite_exato_passa(self):
        session = self._session(preview_ai="claude")
        listener = RelayListener(session, topic="t", max_chars=50)
        listener._handle_message("x" * 50)
        session.handle_complete.assert_called_once()


class OnMessageHookTest(unittest.TestCase):
    """
    on_message existe pro "Recent activity" do main.py conseguir
    mostrar o que o iPhone mandou mesmo quando NADA bateu com nada
    (ex.: wake word desatualizada no telefone) — sem isto, esse caso
    não deixava rastro nenhum, justo a ferramenta feita pra
    diagnosticar por que "não funcionou".
    """

    def _session(self, dictating=False, preview_ai=None, handle_result="ok"):
        session = MagicMock()
        session.dictating = dictating
        session.router.preview.return_value = preview_ai
        session.handle_complete.return_value = handle_result
        return session

    def test_dispara_com_o_texto_bruto_quando_bate(self):
        session = self._session(preview_ai="claude")
        recebidos = []
        listener = RelayListener(session, topic="t", on_message=recebidos.append)
        listener._handle_message("vIsper claude qual é a previsão over")
        self.assertEqual(recebidos, ["vIsper claude qual é a previsão over"])

    def test_dispara_mesmo_quando_nada_bate(self):
        # O caso real que motivou isto: wake word errada/desatualizada
        # -> handle_complete() devolve None -> sem este hook, nada
        # registraria que a mensagem sequer chegou.
        session = self._session(preview_ai=None, handle_result=None)
        recebidos = []
        listener = RelayListener(session, topic="t", on_message=recebidos.append)
        listener._handle_message("iris claude oi over")
        self.assertEqual(recebidos, ["iris claude oi over"])

    def test_dispara_mesmo_quando_bloqueado_pelo_relay(self):
        session = self._session(preview_ai="claude_code")
        recebidos = []
        listener = RelayListener(
            session, topic="t", blocked_ais=["claude_code"], on_message=recebidos.append
        )
        listener._handle_message("vIsper claude code rm -rf algo over")
        self.assertEqual(recebidos, ["vIsper claude code rm -rf algo over"])

    def test_dispara_mesmo_quando_grande_demais(self):
        session = self._session(preview_ai="claude")
        recebidos = []
        listener = RelayListener(
            session, topic="t", max_chars=10, on_message=recebidos.append
        )
        listener._handle_message("x" * 20)
        self.assertEqual(recebidos, ["x" * 20])

    def test_sem_callback_nao_quebra_nada(self):
        session = self._session(preview_ai="claude")
        listener = RelayListener(session, topic="t")
        listener._handle_message("vIsper claude oi over")
        session.handle_complete.assert_called_once()

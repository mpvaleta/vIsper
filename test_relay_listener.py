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
from unittest.mock import patch

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
        self.assertTrue(any("abriu claude" in r for r in results))
        self.assertTrue(any(r.startswith("mandou:") for r in results))

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

        # 3 falhas seguidas dobram (5, 10, 20); reconectar na 4ª
        # reseta; a falha seguinte (5ª) volta a esperar só 5s de novo
        self.assertEqual(sleep_calls, [5, 10, 20, 5])


if __name__ == "__main__":
    unittest.main()

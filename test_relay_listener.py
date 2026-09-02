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

    Usa DictationSession e CommandRouter DE VERDADE, e mede o que
    aconteceu de fato (abriu? colou? apertou Enter?), não quais métodos
    foram chamados. Com uma sessão dublada, a versão anterior destes
    testes passou verde enquanto a trava estava DESLIGADA por um
    engano de dublê — exatamente o tipo de falso OK que não se pode
    ter numa checagem de segurança.
    """

    def _montar(self, blocked=("claude_code",), max_chars=None):
        self.abertos = []
        self.colados = []
        self.enters = []
        ai_actions = {
            nome: (lambda n=nome: self.abertos.append(n))
            for nome in ["claude", "claude_code", "chatgpt", "perplexity", "gemini"]
        }
        session = DictationSession(
            router=CommandRouter(ai_actions),
            paste_action=self.colados.append,
            send_action=lambda: self.enters.append(1),
        )
        kwargs = {"blocked_ais": list(blocked)}
        if max_chars is not None:
            kwargs["max_chars"] = max_chars
        return RelayListener(session, topic="t", **kwargs), session

    def _nada_aconteceu(self):
        self.assertEqual(self.abertos, [])
        self.assertEqual(self.colados, [])
        self.assertEqual(self.enters, [])

    def test_claude_code_pelo_iphone_e_recusado(self):
        # Abrir o Terminal e digitar nele é execução de comando, não
        # "digitar num chat de IA" — a diferença de gravidade entre as
        # duas é grande demais pra deixar no mesmo balde.
        listener, _ = self._montar()
        resultado = listener._handle_message("vIsper claude code rm -rf algo over")
        self._nada_aconteceu()
        self.assertIn("claude_code", resultado)

    def test_claude_code_declarado_no_cabecalho_tambem_e_recusado(self):
        listener, _ = self._montar()
        resultado = listener._handle_message("#visper-ai=claude_code\nvIsper x over")
        self._nada_aconteceu()
        self.assertIn("claude_code", resultado)

    def test_a_trava_vale_mesmo_com_a_thread_do_mic_fechando_no_meio(self):
        """A checagem mora DENTRO do lock, junto da decisão.

        Fora dele havia uma janela real: o relay pulava a checagem
        quando um ditado estava aberto, mas entre ler `dictating` e
        agir o ditado do mic podia FECHAR — e a mensagem abria
        justamente o alvo proibido."""
        listener, session = self._montar()
        session.dictating = True  # como se o mic tivesse acabado de abrir
        session.buffer = []
        session.dictating = False  # ...e fechado antes da mensagem ser tratada
        resultado = listener._handle_message("vIsper claude code rm -rf algo over")
        self._nada_aconteceu()
        self.assertIn("claude_code", resultado)

    def test_recusa_explica_em_vez_de_sumir_calada(self):
        # Mensagem sumindo sem explicação é indistinguível de "o relay
        # não está funcionando".
        listener, _ = self._montar()
        self.assertTrue(listener._handle_message("vIsper claude code oi"))

    def test_ia_permitida_passa_normalmente(self):
        listener, _ = self._montar()
        resultado = listener._handle_message("vIsper claude qual é a previsão over")
        self.assertEqual(self.abertos, ["claude"])
        self.assertEqual(self.colados, ["qual é a previsão"])
        self.assertEqual(len(self.enters), 1)
        self.assertIn("sent:", resultado)

    def test_com_ditado_ja_aberto_o_texto_e_conteudo_e_nao_alvo(self):
        # Texto durante o ditado é CONTEÚDO — uma frase legítima que
        # por acaso cite "claude code" não pode ser barrada.
        listener, session = self._montar()
        session.handle("vIsper claude")
        self.abertos.clear()
        listener._handle_message("preciso revisar o claude code amanhã over")
        self.assertEqual(self.abertos, [])
        self.assertEqual(self.colados, ["preciso revisar o claude code amanhã"])

    def test_lista_de_bloqueio_vazia_libera_tudo(self):
        listener, _ = self._montar(blocked=())
        listener._handle_message("vIsper claude code oi over")
        self.assertEqual(self.abertos, ["claude_code"])

    def test_mensagem_gigante_e_cortada_antes_de_ser_colada(self):
        listener, _ = self._montar(max_chars=50)
        resultado = listener._handle_message("x" * 51)
        self._nada_aconteceu()
        self.assertIn("too large", resultado)


class CabecalhoDeIaTest(unittest.TestCase):
    """A primeira linha "#visper-ai=<id>" carrega a IA já resolvida.

    Ver CLAUDE.md (limitação 13) e RelayListener._split_ai_header():
    codificar essa certeza como texto livre fazia a trava de segurança
    barrar mensagens legítimas.
    """

    def _build(self, blocked=("claude_code",)):
        self.abertos = []
        self.colados = []
        ai_actions = {
            nome: (lambda n=nome: self.abertos.append(n))
            for nome in ["claude", "claude_code", "chatgpt", "perplexity", "gemini"]
        }
        session = DictationSession(
            router=CommandRouter(ai_actions),
            paste_action=self.colados.append,
            send_action=lambda: None,
        )
        return RelayListener(session, topic="t", blocked_ais=list(blocked)), session

    def test_cabecalho_resolve_a_ia_sem_passar_pelo_roteador(self):
        relay, _ = self._build()
        relay._handle_message("#visper-ai=claude\nvIsper claude code review isso over")
        self.assertEqual(self.abertos, ["claude"])
        self.assertEqual(self.colados, ["code review isso"])

    def test_sem_cabecalho_a_mesma_mensagem_era_barrada(self):
        """Prova que o bug era real: sem a linha do cabeçalho, o
        roteador lê "claude code" e a trava recusa tudo."""
        relay, _ = self._build()
        resultado = relay._handle_message("vIsper claude code review isso over")
        self.assertIn("cannot be opened", resultado)
        self.assertEqual(self.abertos, [])
        self.assertEqual(self.colados, [])

    def test_ia_bloqueada_continua_bloqueada_mesmo_declarada(self):
        """A trava passa a olhar o alvo DECLARADO — que é exatamente o
        que seria aberto —, então declarar não é jeito de escapar dela."""
        relay, _ = self._build()
        resultado = relay._handle_message("#visper-ai=claude_code\nvIsper algo over")
        self.assertIn("claude_code", resultado)
        self.assertIn("cannot be opened", resultado)
        self.assertEqual(self.abertos, [])

    def test_cabecalho_com_ia_inventada_cai_no_caminho_antigo(self):
        relay, _ = self._build()
        relay._handle_message("#visper-ai=nao_existe\nvIsper claude oi over")
        self.assertEqual(self.abertos, ["claude"])
        self.assertEqual(self.colados, ["oi"])

    def test_mensagem_sem_cabecalho_nao_muda_de_comportamento(self):
        relay, _ = self._build()
        relay._handle_message("vIsper gemini me explica isso over")
        self.assertEqual(self.abertos, ["gemini"])
        self.assertEqual(self.colados, ["me explica isso"])

    def test_split_devolve_o_texto_inteiro_quando_nao_ha_cabecalho(self):
        relay, _ = self._build()
        self.assertEqual(
            relay._split_ai_header("vIsper claude oi"), (None, "vIsper claude oi")
        )


class ReconexaoComSinceTest(unittest.TestCase):
    """Mensagem publicada enquanto o Mac está reconectando não pode
    sumir — o telefone mostra "Sent to your Mac" de qualquer jeito
    (o POST pro ntfy deu 200), então uma perda dessas é
    indistinguível de "o Mac ignorou o que eu falei"."""

    def _relay(self, **kw):
        session = MagicMock()
        session.dictating = False
        return RelayListener(session, topic="topico", **kw)

    def test_primeira_conexao_nunca_pede_historico(self):
        """Abrir o app não pode executar o que foi dito antes dele
        existir."""
        relay = self._relay()
        self.assertEqual(relay._subscribe_url(None), "https://ntfy.sh/topico/json")

    def test_sem_mensagem_vista_ainda_nao_pede_historico(self):
        relay = self._relay()
        self.assertEqual(relay._subscribe_url(0.0), "https://ntfy.sh/topico/json")

    def test_reconexao_curta_recupera_a_partir_da_ultima_vista(self):
        relay = self._relay()
        relay._last_message_id = "abc123"
        with patch("relay_listener.time.monotonic", return_value=10.0):
            url = relay._subscribe_url(5.0)
        self.assertEqual(url, "https://ntfy.sh/topico/json?since=abc123")

    def test_queda_longa_demais_nao_reexecuta_comando_velho(self):
        relay = self._relay(backlog_max_seconds=300)
        relay._last_message_id = "abc123"
        with patch("relay_listener.time.monotonic", return_value=1000.0):
            url = relay._subscribe_url(5.0)
        self.assertEqual(url, "https://ntfy.sh/topico/json")

    def test_recuperacao_pode_ser_desligada(self):
        relay = self._relay(backlog_max_seconds=0)
        relay._last_message_id = "abc123"
        with patch("relay_listener.time.monotonic", return_value=6.0):
            self.assertEqual(
                relay._subscribe_url(5.0), "https://ntfy.sh/topico/json"
            )

    def test_mensagem_repetida_pelo_since_nao_e_executada_duas_vezes(self):
        """O ntfy pode reentregar a própria âncora do since=, e
        reexecutar (abrir app, colar, apertar Enter) é irreversível."""
        session = MagicMock()
        session.dictating = False
        session.handle_complete.return_value = "ok"
        relay = RelayListener(session, topic="t")

        linhas = [
            json.dumps({"event": "message", "id": "m1", "message": "vIsper claude oi"}),
            json.dumps({"event": "message", "id": "m1", "message": "vIsper claude oi"}),
            json.dumps({"event": "message", "id": "m2", "message": "vIsper claude tchau"}),
        ]

        def parar():
            relay.running = False

        with patch("relay_listener.requests.get") as get:
            get.return_value = FakeResponse(
                [l.encode() for l in linhas], on_exhausted=parar
            )
            relay.listen_forever()

        self.assertEqual(session.handle_complete.call_count, 2)
        self.assertEqual(relay._last_message_id, "m2")


class CabecalhoMalformadoTest(unittest.TestCase):
    """Um cabeçalho quebrado não pode virar texto colado no chat.

    O casamento da wake word é FUZZY, e "visper" casa dentro do próprio
    "#visper-ai=xyz" — então devolver o texto inteiro quando o id não
    valia fazia o resto do cabeçalho ("ai=xyz") ser colado e o Enter
    apertado, se houvesse um ditado do mic aberto na hora.
    """

    def _build(self):
        self.colados = []
        ai_actions = {"claude": lambda: None, "claude_code": lambda: None}
        session = DictationSession(
            router=CommandRouter(ai_actions),
            paste_action=self.colados.append,
            send_action=lambda: None,
        )
        return RelayListener(session, topic="t"), session

    def test_cabecalho_quebrado_sozinho_nao_cola_nada(self):
        relay, session = self._build()
        session.handle("vIsper claude")
        session.handle("conteúdo do mic")
        relay._handle_message("#visper-ai=xyz")
        self.assertEqual(self.colados, [])
        self.assertTrue(session.dictating)

    def test_cabecalho_quebrado_com_conteudo_ainda_funciona(self):
        relay, _ = self._build()
        relay._handle_message("#visper-ai=xyz\nvIsper claude oi over")
        self.assertEqual(self.colados, ["oi"])

    def test_id_do_ntfy_nunca_entra_cru_na_url(self):
        # O id vem do JSON do servidor; um "&" ali viraria outro
        # parâmetro numa requisição que o app faz sozinho, em loop.
        relay, _ = self._build()
        relay._last_message_id = "a b&c=d"
        with patch("relay_listener.time.monotonic", return_value=1.0):
            url = relay._subscribe_url(0.0)
        self.assertNotIn("&c=", url)
        self.assertIn("since=a%20b%26c%3Dd", url)


class RecuperacaoLimitadaPorIdadeTest(unittest.TestCase):
    """O teto de recuperação tem que ser um LIMITE, não um adiamento."""

    def _relay(self, **kw):
        session = MagicMock()
        session.dictating = False
        return RelayListener(session, topic="topico", **kw)

    def test_queda_longa_descarta_a_ancora(self):
        # Sem descartar, o próximo piscar de 5s pedia `since=` a partir
        # da mesma âncora e reentregava o backlog que o teto tinha
        # acabado de recusar.
        relay = self._relay(backlog_max_seconds=300)
        relay._last_message_id = "abc123"
        with patch("relay_listener.time.monotonic", return_value=1000.0):
            relay._subscribe_url(5.0)          # queda longa: recusa
        self.assertIsNone(relay._last_message_id)
        with patch("relay_listener.time.monotonic", return_value=1006.0):
            url = relay._subscribe_url(1001.0)  # piscar curto logo depois
        self.assertNotIn("since=", url)

    def test_mensagem_velha_demais_nao_e_reexecutada(self):
        relay = self._relay(backlog_max_seconds=300)
        with patch("relay_listener.time.time", return_value=10_000.0):
            self.assertTrue(relay._velha_demais({"time": 9_000.0}))
            self.assertFalse(relay._velha_demais({"time": 9_900.0}))

    def test_sem_data_a_mensagem_passa(self):
        # Recusar por não conseguir datar seria pior que entregar — a
        # janela pedida já foi limitada pelo teto.
        relay = self._relay()
        self.assertFalse(relay._velha_demais({}))
        self.assertFalse(relay._velha_demais({"time": "ontem"}))

    def test_com_recuperacao_desligada_nada_e_descartado_por_idade(self):
        relay = self._relay(backlog_max_seconds=0)
        with patch("relay_listener.time.time", return_value=10_000.0):
            self.assertFalse(relay._velha_demais({"time": 1.0}))

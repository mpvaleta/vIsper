"""
Testes dedicados de dictation.py. Até agora esse arquivo só era
exercitado indiretamente. Cobre a máquina de estados ocioso/ditando,
e especialmente os gatilhos de fechamento novos ("câmbio"/"over"),
incluindo o caso que motivou usar palavra inteira em vez de substring
(over não pode casar dentro de "however"/"discover" no meio do
ditado).
"""

import unittest

from command_router import CommandRouter
from dictation import DictationSession


class DictationSessionTest(unittest.TestCase):
    def _build_session(self, calls, with_sounds=False):
        ai_actions = {"claude": lambda: calls.append("abriu_claude")}
        router = CommandRouter(ai_actions)
        kwargs = {}
        if with_sounds:
            kwargs["on_open"] = lambda: calls.append("som_abriu")
            kwargs["on_send"] = lambda: calls.append("som_mandou")
            kwargs["on_cancel"] = lambda: calls.append("som_cancelou")
        return DictationSession(
            router=router,
            paste_action=lambda t: calls.append(("colou", t)),
            send_action=lambda: calls.append("mandou_enter"),
            **kwargs,
        )

    def test_abre_e_entra_em_modo_ditado(self):
        calls = []
        session = self._build_session(calls)
        result = session.handle("vIsper claude")
        self.assertTrue(session.dictating)
        self.assertIn("abriu_claude", calls)
        self.assertIn("opened claude", result)

    def test_conteudo_vai_pro_buffer_sem_mandar_ainda(self):
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        result = session.handle("isso é o que eu quero ditar")
        self.assertTrue(session.dictating)
        self.assertNotIn("mandou_enter", calls)
        self.assertEqual(result, "dictating…")

    def test_fecha_com_a_wake_word_de_novo(self):
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        session.handle("conteudo do ditado")
        session.handle("vIsper")
        self.assertFalse(session.dictating)
        self.assertIn(("colou", "conteudo do ditado"), calls)
        self.assertIn("mandou_enter", calls)

    def test_fecha_com_cambio(self):
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        session.handle("conteudo em portugues")
        session.handle("câmbio")
        self.assertFalse(session.dictating)
        self.assertIn(("colou", "conteudo em portugues"), calls)

    def test_fecha_com_over(self):
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        session.handle("some content in english")
        session.handle("over")
        self.assertFalse(session.dictating)
        self.assertIn(("colou", "some content in english"), calls)

    def test_over_nao_fecha_por_acidente_dentro_de_however(self):
        # o motivo de tudo isso existir: ditar uma frase com "however"
        # não pode ser confundido com o gatilho de fechamento "over"
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        session.handle("however, I think this works")
        self.assertTrue(session.dictating, "não devia ter fechado — 'over' está dentro de 'however'")
        self.assertNotIn("mandou_enter", calls)
        session.handle("over")  # agora sim fecha, de propósito
        self.assertFalse(session.dictating)

    def test_fecha_sem_conteudo_nao_cola_nem_manda(self):
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        result = session.handle("over")
        self.assertFalse(session.dictating)
        self.assertNotIn("mandou_enter", calls)
        self.assertEqual(result, "nothing to send — the dictation was empty")

    def test_texto_sem_wake_word_enquanto_ocioso_nao_faz_nada(self):
        calls = []
        session = self._build_session(calls)
        result = session.handle("oi, tudo bem?")
        self.assertFalse(session.dictating)
        self.assertIsNone(result)
        self.assertEqual(calls, [])

    def test_conteudo_colado_com_over_no_mesmo_trecho_nao_se_perde(self):
        # Regressão: terminar a frase e já emendar "over" sem pausa faz
        # os dois caírem no MESMO chunk transcrito pelo Whisper. Antes
        # dessa correção, o trecho inteiro era descartado (só o buffer
        # de chamadas anteriores contava) e a sessão "mandava" vazio.
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        result = session.handle("and that is the final summary over")
        self.assertFalse(session.dictating)
        self.assertIn(("colou", "and that is the final summary"), calls)
        self.assertIn("mandou_enter", calls)
        self.assertTrue(result.startswith("sent:"))

    def test_conteudo_colado_com_cambio_preserva_acento_original(self):
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        session.handle("Não esqueça da reunião de amanhã câmbio")
        self.assertIn(("colou", "Não esqueça da reunião de amanhã"), calls)

    def test_conteudo_colado_combina_com_buffer_de_chamadas_anteriores(self):
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        session.handle("primeira parte")
        session.handle("segunda parte over")
        self.assertIn(("colou", "primeira parte segunda parte"), calls)

    def test_on_open_e_chamado_ao_abrir(self):
        calls = []
        session = self._build_session(calls, with_sounds=True)
        session.handle("vIsper claude")
        self.assertIn("som_abriu", calls)
        self.assertNotIn("som_mandou", calls)

    def test_on_send_e_chamado_ao_mandar_com_conteudo(self):
        calls = []
        session = self._build_session(calls, with_sounds=True)
        session.handle("vIsper claude")
        session.handle("algum conteudo")
        session.handle("over")
        self.assertIn("som_mandou", calls)

    def test_on_send_nao_e_chamado_ao_cancelar_sem_conteudo(self):
        calls = []
        session = self._build_session(calls, with_sounds=True)
        session.handle("vIsper claude")
        session.handle("over")
        self.assertNotIn("som_mandou", calls)

    def test_sem_callbacks_de_som_continua_funcionando_normalmente(self):
        # on_open/on_send são opcionais (None por padrão) — sessão
        # criada sem eles (with_sounds=False, o padrão) não deve
        # quebrar em nenhum dos dois pontos.
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        session.handle("conteudo qualquer")
        session.handle("over")
        self.assertIn(("colou", "conteudo qualquer"), calls)

    def test_conteudo_na_abertura_no_mesmo_trecho_nao_se_perde(self):
        # Regressão simétrica à do fechamento: dizer "vIsper claude" +
        # a pergunta de verdade tudo numa respiração só (mesmo chunk
        # do Whisper) não podia perder o conteúdo — antes, só o nome
        # da IA era usado pra abrir e o resto sumia.
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude qual é a previsão do tempo hoje?")
        self.assertTrue(session.dictating)
        session.handle("over")
        self.assertIn(("colou", "qual é a previsão do tempo hoje?"), calls)

    def test_conteudo_na_abertura_combina_com_falas_seguintes(self):
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude primeira parte")
        session.handle("segunda parte over")
        self.assertIn(("colou", "primeira parte segunda parte"), calls)

    def test_abrir_so_com_o_nome_da_ia_continua_sem_conteudo_no_buffer(self):
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        self.assertEqual(session.buffer, [])

    def test_abrir_e_fechar_no_MESMO_trecho_manda_na_hora(self):
        # Regressão: o pedido inteiro numa respiração só ("vIsper
        # claude <pergunta> over") é o jeito mais natural de usar isso,
        # e era o único caso que nenhuma das duas correções anteriores
        # pegava — elas cuidavam da abertura e do fechamento
        # separadamente. O "over" ia pro buffer como conteúdo: o
        # ditado ficava aberto pra sempre esperando um fechamento que
        # já tinha sido dito, e quando enfim fechasse a palavra "over"
        # ia colada no texto mandado pra IA.
        calls = []
        session = self._build_session(calls)
        result = session.handle("vIsper claude qual é a previsão do tempo over")
        self.assertIn("abriu_claude", calls)
        self.assertFalse(session.dictating, "o 'over' no mesmo trecho tinha que fechar")
        self.assertIn(("colou", "qual é a previsão do tempo"), calls)
        self.assertIn("mandou_enter", calls)
        self.assertIn("opened claude", result)
        self.assertIn("sent:", result)

    def test_abrir_e_fechar_no_mesmo_trecho_toca_os_dois_earcons(self):
        calls = []
        session = self._build_session(calls, with_sounds=True)
        session.handle("vIsper claude manda ver nisso câmbio")
        self.assertIn("som_abriu", calls)
        self.assertIn("som_mandou", calls)

    def test_abrir_com_gatilho_de_fechamento_e_nada_mais_nao_manda_vazio(self):
        # "vIsper claude over" abre e fecha sem conteúdo nenhum — não
        # pode colar/mandar string vazia, nem tocar o earcon de envio.
        calls = []
        session = self._build_session(calls, with_sounds=True)
        session.handle("vIsper claude over")
        self.assertFalse(session.dictating)
        self.assertNotIn("mandou_enter", calls)
        self.assertNotIn("som_mandou", calls)
        self.assertEqual([c for c in calls if isinstance(c, tuple)], [])

    def test_fechar_so_com_o_gatilho_continua_sem_conteudo(self):
        # Garante que a correção não inventa conteúdo quando não há
        # nada de verdade antes do gatilho (mesmo caso do teste
        # original test_fecha_sem_conteudo_nao_cola_nem_manda, agora
        # com "vIsper" em vez de "over" fechando).
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        result = session.handle("vIsper")
        self.assertNotIn("mandou_enter", calls)
        self.assertEqual(result, "nothing to send — the dictation was empty")


if __name__ == "__main__":
    unittest.main()


class CancelamentoTest(unittest.TestCase):
    """"vIsper, cancela" — a saída NÃO destrutiva do ditado.

    Antes disso o ditado só tinha uma saída, e ela mandava: se a
    transcrição saísse errada, a única forma de não mandar era matar o
    app. O risco desta funcionalidade é o simétrico (cancelar sem
    querer e perder o que foi ditado), e é por isso que a palavra de
    cancelar precisa vir COLADA na wake word — os testes de falso
    positivo abaixo são a parte que importa.
    """

    def _build_session(self, calls, with_sounds=False):
        ai_actions = {"claude": lambda: calls.append("abriu_claude")}
        router = CommandRouter(ai_actions)
        kwargs = {}
        if with_sounds:
            kwargs["on_send"] = lambda: calls.append("som_mandou")
            kwargs["on_cancel"] = lambda: calls.append("som_cancelou")
        return DictationSession(
            router=router,
            paste_action=lambda t: calls.append(("colou", t)),
            send_action=lambda: calls.append("mandou_enter"),
            **kwargs,
        )

    def test_cancela_joga_o_ditado_fora_sem_colar_nem_mandar(self):
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        session.handle("uma ideia que eu já mudei de ideia")
        resultado = session.handle("vIsper cancela")

        self.assertFalse(session.dictating)
        self.assertEqual(session.buffer, [])
        self.assertNotIn("mandou_enter", calls)
        self.assertFalse(any(isinstance(c, tuple) for c in calls))
        self.assertIn("cancelled", resultado)

    def test_cancelar_volta_pro_ocioso_e_deixa_ditar_de_novo(self):
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        session.handle("texto descartado")
        session.handle("vIsper cancela")

        session.handle("vIsper claude")
        session.handle("agora vai")
        session.handle("over")
        # O que foi cancelado não pode voltar junto com o próximo.
        self.assertIn(("colou", "agora vai"), calls)

    def test_cancelar_toca_um_som_DIFERENTE_de_mandar(self):
        calls = []
        session = self._build_session(calls, with_sounds=True)
        session.handle("vIsper claude")
        session.handle("alguma coisa")
        session.handle("vIsper cancela")
        self.assertIn("som_cancelou", calls)
        self.assertNotIn("som_mandou", calls)

    def test_cancelar_sem_nada_ditado_ainda_avisa(self):
        calls = []
        session = self._build_session(calls, with_sounds=True)
        session.handle("vIsper claude")
        resultado = session.handle("vIsper cancela")
        self.assertFalse(session.dictating)
        self.assertIn("cancelled", resultado)
        # Feedback de "não tinha nada mesmo" também é feedback: sem ele
        # dá pra achar que o comando não foi ouvido.
        self.assertIn("som_cancelou", calls)

    def test_falar_em_cancelar_NO_MEIO_do_ditado_e_conteudo(self):
        # O caso que fez a regra ser adjacência e não "a palavra em
        # qualquer lugar do trecho": aqui a pessoa está ditando uma
        # mensagem que POR ACASO fala em cancelar. Isso tem que ser
        # mandado, não apagado.
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        session.handle("preciso cancelar a reserva de amanhã")
        session.handle("over")
        self.assertIn(("colou", "preciso cancelar a reserva de amanhã"), calls)

    def test_cancelar_no_fim_da_frase_ainda_MANDA_em_vez_de_apagar(self):
        # Pior versão do caso acima: a wake word fecha o ditado no
        # MESMO trecho em que a palavra "cancelar" aparece — só que
        # antes dela, não depois. Fechamento normal.
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        session.handle("preciso cancelar a reserva vIsper")
        self.assertIn(("colou", "preciso cancelar a reserva"), calls)
        self.assertIn("mandou_enter", calls)

    def test_cancela_sozinho_sem_a_wake_word_e_conteudo(self):
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")
        session.handle("cancela")
        session.handle("over")
        self.assertIn(("colou", "cancela"), calls)

    def test_cancelar_na_MESMA_respiracao_que_abriu(self):
        # "vIsper claude ... vIsper cancela" numa tacada — improvável,
        # mas é o mesmo caminho de código do abre-e-fecha-junto, então
        # tem que se comportar igual: abre, e não manda nada.
        calls = []
        session = self._build_session(calls)
        resultado = session.handle("vIsper claude isso aqui vIsper cancela")
        self.assertIn("abriu_claude", calls)
        self.assertFalse(session.dictating)
        self.assertNotIn("mandou_enter", calls)
        self.assertIn("cancelled", resultado)

    def test_variacoes_de_pontuacao_e_acento_da_transcricao(self):
        # O Whisper transcreve com vírgula/ponto e com ou sem
        # maiúscula; nenhuma dessas formas pode deixar de cancelar.
        for fala in ("vIsper, cancela", "Visper. Cancela.", "visper cancelar",
                     "vIsper esquece isso"):
            with self.subTest(fala=fala):
                calls = []
                session = self._build_session(calls)
                session.handle("vIsper claude")
                session.handle("conteúdo qualquer")
                session.handle(fala)
                self.assertFalse(session.dictating, fala)
                self.assertNotIn("mandou_enter", calls)


class AberturaToleranteTest(unittest.TestCase):
    """
    A tolerância a erro de transcrição vale só pra ABRIR (router);
    FECHAR continua exato — fechar por engano manda a mensagem pela
    metade, que é destrutivo, enquanto abrir por engano só abre uma
    aba à toa. Estes testes fixam a assimetria de propósito.
    """

    def _build(self, calls):
        router = CommandRouter({"claude": lambda: calls.append("abriu")})
        return DictationSession(
            router=router,
            paste_action=lambda t: calls.append(("colou", t)),
            send_action=lambda: calls.append("enter"),
        )

    def test_respiracao_unica_com_wake_word_transcrita_errada(self):
        # "whisper claude ... over" numa chamada só: abre pelo fuzzy,
        # o conteúdo entra, e o "over" (exato) fecha e manda.
        calls = []
        session = self._build(calls)

        session.handle("whisper claude me lembra da reunião over")

        self.assertIn("abriu", calls)
        self.assertIn(("colou", "me lembra da reunião"), calls)
        self.assertIn("enter", calls)
        self.assertFalse(session.dictating)

    def test_whisper_durante_o_ditado_e_conteudo_nao_fechamento(self):
        # Se o fechamento usasse fuzzy, falar a palavra "whisper" no
        # meio de um ditado (ex.: falando sobre o próprio modelo)
        # cortaria e mandaria cedo. Tem que virar conteúdo.
        calls = []
        session = self._build(calls)
        session.dictating = True

        resultado = session.handle("o modelo whisper é o que transcreve")
        self.assertEqual(resultado, "dictating…")
        self.assertTrue(session.dictating)

        session.handle("over")
        self.assertIn(("colou", "o modelo whisper é o que transcreve"), calls)


class HandleCompleteTest(unittest.TestCase):
    """
    handle_complete() é o caminho do relay do iPhone (ver
    relay_listener.py) — cada chamada já é a mensagem INTEIRA, então,
    ao contrário de handle(), o conteúdo não é vasculhado atrás de
    CLOSE_TRIGGERS no meio do texto; só um marcador GRUDADO NO FIM é
    removido. Regressão real que motivou isto: o app de iPhone
    (docs/index.html, buildMessage()) gruda " over" no fim de TODA
    mensagem só pra sinalizar "isto é tudo" — com handle() comum,
    conteúdo real contendo "over"/"câmbio" (ex.: "let's talk this
    over", "qual é o câmbio do dólar hoje") era cortado ali no meio, e
    o texto TRUNCADO já tinha sido colado e o Enter já apertado antes
    de qualquer um perceber.
    """

    def _build_session(self, calls, with_sounds=False):
        ai_actions = {"claude": lambda: calls.append("abriu_claude")}
        router = CommandRouter(ai_actions)
        kwargs = {}
        if with_sounds:
            kwargs["on_open"] = lambda: calls.append("som_abriu")
            kwargs["on_send"] = lambda: calls.append("som_mandou")
        return DictationSession(
            router=router,
            paste_action=lambda t: calls.append(("colou", t)),
            send_action=lambda: calls.append("mandou_enter"),
            **kwargs,
        )

    def test_abre_e_manda_de_uma_vez(self):
        calls = []
        session = self._build_session(calls)
        resultado = session.handle_complete("vIsper claude confirma a reuniao over")
        self.assertIn("abriu_claude", calls)
        self.assertIn(("colou", "confirma a reuniao"), calls)
        self.assertIn("mandou_enter", calls)
        self.assertFalse(session.dictating)
        self.assertTrue(resultado.startswith("opened claude"))
        self.assertIn("sent:", resultado)

    def test_conteudo_contendo_over_no_meio_nao_e_truncado(self):
        # A regressão exata: "over" faz parte do que a pessoa quis
        # dizer, não é o marcador (que é o SEGUNDO "over", grudado
        # pelo app). O texto inteiro tem que ser colado.
        calls = []
        session = self._build_session(calls)
        session.handle_complete("vIsper claude let's talk this over quickly over")
        self.assertIn(("colou", "let's talk this over quickly"), calls)
        self.assertIn("mandou_enter", calls)

    def test_conteudo_contendo_cambio_no_meio_nao_e_truncado(self):
        calls = []
        session = self._build_session(calls)
        session.handle_complete("vIsper claude qual e o cambio do dolar hoje over")
        self.assertIn(("colou", "qual e o cambio do dolar hoje"), calls)
        self.assertIn("mandou_enter", calls)

    def test_so_wake_e_ia_sem_conteudo_nao_manda_vazio(self):
        # "vIsper claude over" — só testando a conexão (ver README),
        # sem conteúdo de verdade. O único "over" é o marcador.
        calls = []
        session = self._build_session(calls)
        resultado = session.handle_complete("vIsper claude over")
        self.assertIn("abriu_claude", calls)
        self.assertNotIn("mandou_enter", calls)
        self.assertFalse(any(c[0] == "colou" for c in calls if isinstance(c, tuple)))
        self.assertIn("nothing to send", resultado)

    def test_sem_wake_word_nao_faz_nada(self):
        calls = []
        session = self._build_session(calls)
        self.assertIsNone(session.handle_complete("qualquer coisa aleatoria over"))
        self.assertEqual(calls, [])

    def test_mensagem_chegando_com_ditado_de_mic_ja_aberto_fecha_na_hora(self):
        # Uma mensagem do iPhone não pode ficar pendurada esperando um
        # fechamento que ela nunca vai mandar de novo.
        calls = []
        session = self._build_session(calls)
        session.handle("vIsper claude")  # abre pelo mic
        session.handle("primeira parte ditada pelo mic")
        self.assertTrue(session.dictating)

        resultado = session.handle_complete("resto mandado pelo iphone over")

        self.assertFalse(session.dictating)
        self.assertIn(
            ("colou", "primeira parte ditada pelo mic resto mandado pelo iphone"),
            calls,
        )
        self.assertIn("sent:", resultado)

    def test_texto_vazio_nao_faz_nada(self):
        calls = []
        session = self._build_session(calls)
        self.assertIsNone(session.handle_complete("   "))
        self.assertEqual(calls, [])

    def test_on_open_e_on_send_disparam_normalmente(self):
        calls = []
        session = self._build_session(calls, with_sounds=True)
        session.handle_complete("vIsper claude oi over")
        self.assertIn("som_abriu", calls)
        self.assertIn("som_mandou", calls)

    def test_lock_permite_chamadas_concorrentes_sem_perder_conteudo(self):
        # Regressão: mic e iPhone rodam em THREADS diferentes sobre a
        # MESMA sessão (main.py). Sem lock, duas chamadas quase
        # simultâneas podiam ler self.dictating==False antes de
        # qualquer uma escrever True, abrindo duas IAs e perdendo o
        # conteúdo de uma delas. Não reproduz o timing exato da corrida
        # (isso exigiria hardware real), mas prova que o lock existe e
        # serializa: nenhuma chamada concorrente é perdida ou
        # corrompida — todo conteúdo mandado aparece colado em algum
        # dos resultados.
        import threading

        calls = []
        lock = threading.Lock()

        def calls_append(item):
            with lock:
                calls.append(item)

        ai_actions = {"claude": lambda: calls_append("abriu_claude")}
        router = CommandRouter(ai_actions)
        session = DictationSession(
            router=router,
            paste_action=lambda t: calls_append(("colou", t)),
            send_action=lambda: calls_append("mandou_enter"),
        )
        self.assertTrue(hasattr(session, "_lock"))

        resultados = [None] * 20

        def worker(i):
            resultados[i] = session.handle_complete(f"vIsper claude mensagem {i} over")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Cada uma das 20 mensagens tem que ter sido colada exatamente
        # uma vez — nenhuma perdida, nenhuma duplicada, nenhuma
        # corrompida por interferência de outra thread.
        coladas = [c[1] for c in calls if isinstance(c, tuple) and c[0] == "colou"]
        esperado = [f"mensagem {i}" for i in range(20)]
        self.assertCountEqual(coladas, esperado)
        self.assertFalse(session.dictating)


if __name__ == "__main__":
    unittest.main()

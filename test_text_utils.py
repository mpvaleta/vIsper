import unittest

import text_utils as tu
from text_utils import (
    contains_word,
    find_word,
    fold_accents,
    split_after_word,
    split_before_any,
    strip_trailing_word,
    text_after_word,
)


class FoldAccentsTest(unittest.TestCase):
    def test_remove_acentos_comuns(self):
        self.assertEqual(fold_accents("câmbio"), "cambio")
        self.assertEqual(fold_accents("código"), "codigo")
        self.assertEqual(fold_accents("é"), "e")

    def test_texto_sem_acento_fica_igual(self):
        self.assertEqual(fold_accents("over"), "over")


class ContainsWordTest(unittest.TestCase):
    def test_encontra_palavra_isolada(self):
        self.assertTrue(contains_word("vIsper, câmbio", "câmbio"))
        self.assertTrue(contains_word("ok over", "over"))

    def test_nao_confunde_acento_transcrito_diferente(self):
        # Whisper pode ou não transcrever o acento — os dois têm que bater
        self.assertTrue(contains_word("diz cambio ali", "câmbio"))
        self.assertTrue(contains_word("diz câmbio ali", "cambio"))

    def test_NAO_casa_como_substring_de_outra_palavra(self):
        # o motivo de tudo isso existir: "over" não pode casar dentro
        # dessas palavras comuns em inglês
        self.assertFalse(contains_word("however you look at it", "over"))
        self.assertFalse(contains_word("moreover, this matters", "over"))
        self.assertFalse(contains_word("please discover this", "over"))
        self.assertFalse(contains_word("cover the basics", "over"))

    def test_casa_frase_com_espaco(self):
        self.assertTrue(contains_word("abre o claude code agora", "claude code"))
        self.assertFalse(contains_word("abre o claude agora", "claude code"))

    def test_ignora_maiuscula_minuscula(self):
        self.assertTrue(contains_word("VISPER CLAUDE", "visper"))

    def test_string_vazia_nunca_casa(self):
        self.assertFalse(contains_word("qualquer coisa", ""))


class SplitAfterWordTest(unittest.TestCase):
    def test_retorna_o_que_vem_depois(self):
        self.assertEqual(split_after_word("vIsper claude", "vIsper"), "claude")

    def test_string_vazia_se_nao_achar(self):
        self.assertEqual(split_after_word("nada a ver aqui", "vIsper"), "")

    def test_funciona_com_acento_misto(self):
        self.assertEqual(split_after_word("vIsper claude código", "visper"), "claude codigo")

    def test_so_pontuacao_depois_conta_como_vazio(self):
        # Regressão: o Whisper adiciona pontuação de frase com
        # frequência mesmo em falas curtas — "vIsper." (só a wake
        # word, transcrita com ponto final) tinha que abrir a IA
        # padrão exatamente como "vIsper" sozinho, e não falhava
        # silenciosamente por sobrar "." como se fosse conteúdo.
        for transcript in ["vIsper.", "vIsper,", "vIsper...", "vIsper!", "vIsper?"]:
            with self.subTest(transcript=transcript):
                self.assertEqual(split_after_word(transcript, "vIsper"), "")

    def test_pontuacao_nas_bordas_do_conteudo_e_removida(self):
        self.assertEqual(split_after_word("vIsper, claude", "vIsper"), "claude")
        self.assertEqual(split_after_word("vIsper: claude.", "vIsper"), "claude")

    def test_pontuacao_NAO_ASCII_depois_tambem_conta_como_vazio(self):
        # Regressão: as bordas eram aparadas com
        # `string.whitespace + string.punctuation`, que é só ASCII — e
        # o Whisper transcreve travessão, reticências e aspas curvas de
        # verdade. Com a lista antiga, "vIsper—" deixava "—" sobrando
        # como se fosse conteúdo: o router não achava nome de IA
        # nenhum ali, devolvia None, e a wake word sozinha
        # simplesmente não abria a IA padrão. Mesmo bug do caso
        # "vIsper.", só que pra pontuação não-ASCII.
        for transcript in ["vIsper—", "vIsper…", "vIsper “", "vIsper¿", "vIsper –"]:
            with self.subTest(transcript=transcript):
                self.assertEqual(split_after_word(transcript, "vIsper"), "")


class SplitBeforeAnyTest(unittest.TestCase):
    def test_retorna_o_que_vem_antes_do_primeiro_gatilho(self):
        self.assertEqual(
            split_before_any("and that is the final summary over", ["over", "câmbio"]),
            "and that is the final summary",
        )

    def test_preserva_maiuscula_e_acento_do_original(self):
        # Diferente de split_after_word: isso pode virar conteúdo real
        # colado no chat, então NÃO pode voltar tudo minúsculo/sem acento.
        self.assertEqual(
            split_before_any("Não esqueça da reunião de amanhã câmbio", ["câmbio", "over"]),
            "Não esqueça da reunião de amanhã",
        )

    def test_ignora_acento_so_pra_achar_o_gatilho(self):
        # "cambio" sem acento tem que casar com o gatilho "câmbio"
        # (Whisper pode transcrever com ou sem acento), mas o texto
        # ANTES dele preserva o próprio acento original.
        self.assertEqual(
            split_before_any("café da tarde cambio", ["câmbio"]),
            "café da tarde",
        )

    def test_sem_gatilho_nenhum_retorna_tudo(self):
        self.assertEqual(
            split_before_any("nada de especial aqui", ["over", "câmbio"]),
            "nada de especial aqui",
        )

    def test_gatilho_logo_no_inicio_retorna_vazio(self):
        self.assertEqual(split_before_any("over", ["over"]), "")

    def test_lista_de_palavras_vazia_retorna_tudo(self):
        self.assertEqual(split_before_any("qualquer coisa", []), "qualquer coisa")

    def test_nao_casa_como_substring_de_outra_palavra(self):
        # mesma garantia de contains_word: "over" não pode cortar
        # dentro de "however"
        self.assertEqual(
            split_before_any("however this still works", ["over"]),
            "however this still works",
        )

    def test_preserva_pontuacao_real_no_final_do_conteudo(self):
        # Regressão: diferente de split_after_word (cujo resultado
        # NUNCA é mostrado a ninguém), o que sobra aqui pode virar
        # texto de verdade colado no chat — "!"/"."/"?" ditos pela
        # pessoa não podem sumir só porque estão perto do gatilho.
        self.assertEqual(
            split_before_any("what a great idea! over", ["over"]),
            "what a great idea!",
        )
        self.assertEqual(
            split_before_any("confirma a reuniao de amanha, por favor. over", ["over"]),
            "confirma a reuniao de amanha, por favor.",
        )
        self.assertEqual(
            split_before_any("você tem certeza? câmbio", ["câmbio"]),
            "você tem certeza?",
        )

    def test_caractere_que_muda_de_tamanho_ao_dobrar_nao_desloca_o_corte(self):
        # Regressão séria: a posição do gatilho era achada no texto
        # DOBRADO (minúsculo, sem acento) e usada pra fatiar o texto
        # ORIGINAL. Isso pressupõe que dobrar preserva o comprimento —
        # e não preserva: fold_accents() usa NFKD, que é decomposição
        # de COMPATIBILIDADE, então "…" (U+2026, que o Whisper
        # transcreve de verdade) vira "..." e cresce 2 caracteres. A
        # partir dali todo índice ficava deslocado e o corte saía no
        # lugar errado — "Bom dia… over" virava "Bom dia… ov", ou seja,
        # o gatilho vazava pro texto colado no chat E o conteúdo era
        # comido pela metade.
        self.assertEqual(split_before_any("Bom dia… over", ["over"]), "Bom dia…")
        self.assertEqual(
            split_before_any("Preciso disso… agora câmbio", ["câmbio", "over"]),
            "Preciso disso… agora",
        )
        # ½ e ﬁ também decompõem em mais de um caractere no NFKD
        self.assertEqual(
            split_before_any("são ½ litros over", ["over"]), "são ½ litros"
        )


class StripTrailingWordTest(unittest.TestCase):
    """
    Ver a docstring de strip_trailing_word() em text_utils.py: existe
    pra dictation.DictationSession.handle_complete() poder remover só
    o marcador de fechamento que o app de iPhone GRUDA NO FIM de toda
    mensagem (buildMessage(), docs/index.html), sem tratar uma
    ocorrência de verdade da mesma palavra NO MEIO do conteúdo como se
    fosse o marcador — regressão real: "let's talk this over" (a
    palavra "over" é parte do que a pessoa quis dizer) virava "over"
    sendo cortado ali achando que era o fim, com o "quickly" ou
    qualquer coisa depois PERDIDO e o Enter já apertado.
    """

    def test_remove_so_a_ocorrencia_final(self):
        self.assertEqual(
            strip_trailing_word("confirma a reuniao de amanha over", ["over"]),
            "confirma a reuniao de amanha",
        )

    def test_ocorrencia_real_no_meio_sobrevive(self):
        # A palavra "over" faz parte do que a pessoa quis dizer — só o
        # marcador colado no FIM (o segundo "over") pode sumir.
        self.assertEqual(
            strip_trailing_word("let's talk this over over", ["over"]),
            "let's talk this over",
        )

    def test_cambio_no_meio_da_frase_em_portugues_sobrevive(self):
        self.assertEqual(
            strip_trailing_word("qual e o cambio do dolar hoje over", ["over", "câmbio"]),
            "qual e o cambio do dolar hoje",
        )

    def test_conteudo_e_so_o_marcador_fica_vazio(self):
        # "vIsper claude over" (só testando a conexão, sem conteúdo de
        # verdade) — o único "over" presente É o marcador.
        self.assertEqual(strip_trailing_word("over", ["over"]), "")

    def test_sem_marcador_no_fim_devolve_tudo(self):
        self.assertEqual(
            strip_trailing_word("however this still works", ["over"]),
            "however this still works",
        )

    def test_marcador_nao_e_o_ultimo_token_nao_conta(self):
        # "over" aparece, mas não é a ÚLTIMA palavra — não é o
        # marcador, então nada é removido.
        self.assertEqual(
            strip_trailing_word("over and out, team", ["over"]),
            "over and out, team",
        )

    def test_preserva_maiuscula_acento_e_pontuacao_do_que_sobra(self):
        self.assertEqual(
            strip_trailing_word("Não esqueça da reunião de amanhã! over", ["over"]),
            "Não esqueça da reunião de amanhã!",
        )

    def test_ignora_acento_e_caixa_do_marcador(self):
        self.assertEqual(
            strip_trailing_word("preciso trocar dinheiro CÂMBIO", ["câmbio"]),
            "preciso trocar dinheiro",
        )

    def test_lista_de_palavras_vazia_devolve_tudo(self):
        self.assertEqual(strip_trailing_word("qualquer coisa over", []), "qualquer coisa over")

    def test_string_vazia_devolve_vazia(self):
        self.assertEqual(strip_trailing_word("", ["over"]), "")

    def test_caractere_que_muda_de_tamanho_ao_dobrar_nao_desloca_o_corte(self):
        self.assertEqual(
            strip_trailing_word("Bom dia… tudo bem over", ["over"]), "Bom dia… tudo bem"
        )


class TextAfterWordTest(unittest.TestCase):
    def test_retorna_o_que_vem_depois_preservando_tudo(self):
        self.assertEqual(
            text_after_word("vIsper claude qual é a previsão do tempo?", "claude"),
            "qual é a previsão do tempo?",
        )

    def test_string_vazia_se_nao_achar(self):
        self.assertEqual(text_after_word("nada a ver aqui", "vIsper"), "")

    def test_preserva_maiuscula_e_acento(self):
        self.assertEqual(
            text_after_word("vIsper Claude Não esqueça de responder", "claude"),
            "Não esqueça de responder",
        )

    def test_nada_depois_retorna_vazio(self):
        self.assertEqual(text_after_word("vIsper claude", "claude"), "")

    def test_ignora_acento_so_pra_achar_a_palavra(self):
        self.assertEqual(text_after_word("abre o código python", "codigo"), "python")

    def test_nao_casa_como_substring_de_outra_palavra(self):
        self.assertEqual(text_after_word("discover something new", "over"), "")

    def test_pontuacao_colada_na_palavra_e_removida_mas_pontuacao_final_fica(self):
        # "claude," — a vírgula é artefato de como a palavra foi dita
        # (pausa depois do nome), não conteúdo; mas "!" no fim de uma
        # frase real dita pela pessoa tem que sobreviver.
        self.assertEqual(
            text_after_word("vIsper claude, não esqueça de confirmar!", "claude"),
            "não esqueça de confirmar!",
        )
        self.assertEqual(
            text_after_word("vIsper claude: qual é a previsão do tempo hoje?", "claude"),
            "qual é a previsão do tempo hoje?",
        )

    def test_caractere_que_muda_de_tamanho_ao_dobrar_nao_come_o_conteudo(self):
        # Mesma regressão de SplitBeforeAnyTest, do outro lado do
        # corte: com "…" ANTES da palavra procurada, os índices
        # deslocavam e o conteúdo saía com os primeiros caracteres
        # comidos ("qual é..." virava "ual é...") — texto corrompido
        # colado direto no chat da IA.
        self.assertEqual(
            text_after_word("vIsper… claude qual é a previsão do tempo", "claude"),
            "qual é a previsão do tempo",
        )
        self.assertEqual(
            text_after_word("vIsper… claude, confirma isso!", "claude"),
            "confirma isso!",
        )


class FindWordTest(unittest.TestCase):
    def test_devolve_a_posicao_da_primeira_ocorrencia(self):
        self.assertEqual(find_word("claude e nao o perplexity", "claude"), 0)
        self.assertEqual(find_word("claude e nao o perplexity", "perplexity"), 15)

    def test_none_quando_nao_aparece_como_palavra_inteira(self):
        self.assertIsNone(find_word("discover something", "over"))
        self.assertIsNone(find_word("qualquer coisa", "claude"))

    def test_ignora_acento_e_maiuscula_pra_achar(self):
        self.assertEqual(find_word("abre o CÓDIGO agora", "codigo"), 7)

    def test_palavra_vazia_nunca_acha(self):
        self.assertIsNone(find_word("qualquer coisa", ""))


class StartsWithWordTest(unittest.TestCase):
    """Existe pro cancelamento ("vIsper, cancela") poder exigir
    ADJACÊNCIA em vez de "a palavra em algum lugar do trecho" — ver
    dictation._is_cancel()."""

    def test_casa_no_comeco(self):
        self.assertTrue(tu.starts_with_word("cancela isso", "cancela"))

    def test_ignora_pontuacao_e_espaco_antes(self):
        self.assertTrue(tu.starts_with_word("  , cancela", "cancela"))

    def test_ignora_acento_e_caixa(self):
        self.assertTrue(tu.starts_with_word("CÂMBIO agora", "cambio"))

    def test_nao_casa_no_meio(self):
        self.assertFalse(
            tu.starts_with_word("preciso cancelar isso", "cancelar")
        )

    def test_nao_casa_como_prefixo_de_outra_palavra(self):
        # "cancelamento" começa com "cancela", mas não É "cancela".
        self.assertFalse(
            tu.starts_with_word("cancelamento da reserva", "cancela")
        )

    def test_frase_de_varias_palavras(self):
        self.assertTrue(tu.starts_with_word("forget it please", "forget it"))
        self.assertFalse(tu.starts_with_word("please forget it", "forget it"))

    def test_vazio_nunca_casa(self):
        self.assertFalse(tu.starts_with_word("qualquer coisa", ""))
        self.assertFalse(tu.starts_with_word("", "cancela"))


if __name__ == "__main__":
    unittest.main()


class FindTriggerSpanTest(unittest.TestCase):
    """
    find_trigger_span() é a base da detecção tolerante da ABERTURA:
    devolve o intervalo casado NO TEXTO ORIGINAL (via mapa de índices,
    regra da casa) pra quem chama poder fatiar o leftover mesmo quando
    o que está escrito ("cloud") difere do gatilho ("claude").
    """

    def test_exato_devolve_o_intervalo_no_original(self):
        span = tu.find_trigger_span("vIsper claude qual é o tempo", "claude")
        self.assertIsNotNone(span)
        start, end, ratio = span
        self.assertEqual("vIsper claude qual é o tempo"[start:end], "claude")
        self.assertEqual(ratio, 1.0)

    def test_intervalo_sobrevive_a_dobra_que_muda_o_comprimento(self):
        # "…" vira "..." ao dobrar (+2). Sem o mapa de índices, o
        # intervalo viria deslocado e o fatiamento comeria conteúdo —
        # o mesmo bug já corrigido em text_after_word()/split_before_any().
        texto = "Ok… vIsper claude qual é a previsão"
        span = tu.find_trigger_span(texto, "claude")
        start, end, _ = span
        self.assertEqual(texto[start:end], "claude")
        self.assertEqual(texto[end:].strip(), "qual é a previsão")

    def test_pontuacao_colada_fica_fora_do_intervalo(self):
        texto = "vIsper, claude."
        span = tu.find_trigger_span(texto, "claude")
        start, end, _ = span
        self.assertEqual(texto[start:end], "claude")

    def test_frase_de_duas_palavras(self):
        texto = "vIsper claude code roda os testes"
        span = tu.find_trigger_span(texto, "claude code")
        start, end, _ = span
        self.assertEqual(texto[start:end], "claude code")

    def test_aproximado_pega_as_transcricoes_erradas_reais(self):
        # As variantes que o Whisper produz DE VERDADE pra essas
        # palavras — cada uma fazia o comando falhar calado antes.
        for escrito, gatilho in [
            ("whisper", "visper"),   # wake word inventada -> palavra real
            ("vesper", "visper"),
            ("cloud", "claude"),     # pronúncia PT de Claude
            ("clode", "claude"),
            ("claudio", "claude"),
            ("chad gpt", "chat gpt"),
        ]:
            with self.subTest(escrito=escrito):
                span = tu.find_trigger_span(escrito, gatilho, threshold=0.72)
                self.assertIsNotNone(span, f"{escrito!r} devia casar com {gatilho!r}")

    def test_aproximado_rejeita_palavras_de_ditado_proximas(self):
        for escrito, gatilho in [
            ("dispersar", "visper"),  # 0.67, a colisão mais próxima medida
            ("sempre", "visper"),
            ("nuvem", "claude"),
            ("cansado", "claude"),
        ]:
            with self.subTest(escrito=escrito):
                self.assertIsNone(
                    tu.find_trigger_span(escrito, gatilho, threshold=0.72)
                )

    def test_frase_nao_casa_pelo_elo_fraco(self):
        # Regressão real da primeira versão: a janela era comparada
        # EMENDADA, então "claude nao" vs "claude code" dava 0.76 (o
        # "claude" compartilhado dominava a conta) e "vIsper claude não
        # esqueça..." abria o Claude Code, comendo o "não" do conteúdo.
        # Palavra a palavra, "nao"×"code" reprova sozinho.
        self.assertIsNone(
            tu.find_trigger_span("claude não esqueça", "claude code", threshold=0.72)
        )

    def test_threshold_1_e_exato_puro(self):
        self.assertIsNone(tu.find_trigger_span("whisper claude", "visper"))
        self.assertIsNotNone(tu.find_trigger_span("vIsper claude", "visper"))

    def test_palavra_curta_nunca_casa_aproximado(self):
        # Com 3 letras, uma letra diferente já é um terço da palavra.
        self.assertIsNone(tu.find_trigger_span("io", "ia", threshold=0.72))

    def test_mais_a_esquerda_ganha(self):
        texto = "cloud e depois claude"
        span = tu.find_trigger_span(texto, "claude", threshold=0.72)
        start, end, ratio = span
        self.assertEqual(texto[start:end], "cloud")
        self.assertLess(ratio, 1.0)

    def test_gatilho_vazio_nao_casa(self):
        self.assertIsNone(tu.find_trigger_span("qualquer texto", ""))


class TrimHelpersTest(unittest.TestCase):
    def test_trim_for_decision_dobra_e_apara_pontuacao(self):
        self.assertEqual(tu.trim_for_decision(" — Câmbio! "), "cambio")
        self.assertEqual(tu.trim_for_decision(" …— "), "")

    def test_trim_for_content_preserva_fim_de_frase(self):
        # Assimetria de text_after_word(): pontuação some da esquerda
        # (artefato), fica na direita (fim de frase real da pessoa).
        self.assertEqual(
            tu.trim_for_content(", qual é a previsão?"), "qual é a previsão?"
        )

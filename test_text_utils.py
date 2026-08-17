import unittest

from text_utils import (
    contains_word,
    fold_accents,
    split_after_word,
    split_before_any,
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


if __name__ == "__main__":
    unittest.main()

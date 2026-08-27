"""
Testa user_settings.py — a sobreposição de configuração pessoal que
mora FORA do repositório.

Aponta VISPER_SETTINGS_PATH pra um diretório temporário em todos os
testes: o arquivo de verdade (~/Library/Application Support/vIsper/
settings.json) nunca é lido nem escrito aqui, mesmo rodando num Mac.

O que importa cobrir, porque é o que protege o app de quebrar por causa
de um arquivo de configuração ruim: valor com tipo errado é descartado
SOZINHO (o resto do arquivo continua valendo), e arquivo ilegível/
quebrado cai nos padrões em vez de derrubar tudo.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

import user_settings


class SettingsTestCase(unittest.TestCase):
    """Base: cada teste ganha um settings.json próprio e descartável."""

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

    def escrever(self, conteudo):
        if isinstance(conteudo, str):
            self.path.write_text(conteudo, encoding="utf-8")
        else:
            self.path.write_text(json.dumps(conteudo), encoding="utf-8")


class LeituraTest(SettingsTestCase):
    def test_sem_arquivo_devolve_vazio(self):
        self.assertEqual(user_settings.load_settings(), {})

    def test_json_quebrado_nao_levanta(self):
        # Num .app empacotado não há Terminal: uma exceção aqui viraria
        # um app que simplesmente não abre, sem nenhuma pista do porquê.
        self.escrever("{isso não é json")
        self.assertEqual(user_settings.load_settings(), {})

    def test_json_valido_mas_nao_e_objeto(self):
        self.escrever("[1, 2, 3]")
        self.assertEqual(user_settings.load_settings(), {})

    def test_le_valores_validos(self):
        self.escrever({"WAKE_WORD": "Vésper", "NTFY_TOPIC": "visper-abc"})
        self.assertEqual(
            user_settings.load_settings(),
            {"WAKE_WORD": "Vésper", "NTFY_TOPIC": "visper-abc"},
        )

    def test_chave_desconhecida_e_ignorada(self):
        # Um settings.json não deve conseguir injetar configuração que o
        # código não conhece.
        self.escrever({"WAKE_WORD": "Íris", "COISA_INVENTADA": "x"})
        self.assertEqual(user_settings.load_settings(), {"WAKE_WORD": "Íris"})

    def test_valor_com_tipo_errado_cai_sozinho(self):
        # O ponto: descarta só o campo ruim, não o arquivo inteiro. Errar
        # o tipo de um campo e perder a configuração toda sem entender o
        # porquê seria bem pior.
        self.escrever({"WAKE_WORD": 42, "NTFY_TOPIC": "visper-ok"})
        self.assertEqual(user_settings.load_settings(), {"NTFY_TOPIC": "visper-ok"})

    def test_lista_de_gatilhos_precisa_ser_de_strings(self):
        self.escrever({"CLOSE_TRIGGERS": ["over", 7]})
        self.assertEqual(user_settings.load_settings(), {})
        self.escrever({"CLOSE_TRIGGERS": ["over", "câmbio"]})
        self.assertEqual(
            user_settings.load_settings(), {"CLOSE_TRIGGERS": ["over", "câmbio"]}
        )

    def test_ai_triggers_precisa_ser_mapa_de_listas(self):
        self.escrever({"AI_TRIGGERS": {"claude": "claude"}})  # string, não lista
        self.assertEqual(user_settings.load_settings(), {})
        self.escrever({"AI_TRIGGERS": {}})  # vazio deixaria o app sem IA nenhuma
        self.assertEqual(user_settings.load_settings(), {})
        self.escrever({"AI_TRIGGERS": {"claude": ["claude", "cláudio"]}})
        self.assertEqual(
            user_settings.load_settings(),
            {"AI_TRIGGERS": {"claude": ["claude", "cláudio"]}},
        )

    def test_grupos_de_dispositivo_validados(self):
        self.escrever({"PREFERRED_INPUT_DEVICES": [{"keywords": []}]})  # sem keyword
        self.assertEqual(user_settings.load_settings(), {})
        self.escrever(
            {"PREFERRED_INPUT_DEVICES": [{"keywords": ["dji"], "bluetooth": "sim"}]}
        )  # bluetooth deveria ser bool
        self.assertEqual(user_settings.load_settings(), {})
        bom = [{"keywords": ["dji"], "bluetooth": False}]
        self.escrever({"PREFERRED_INPUT_DEVICES": bom})
        self.assertEqual(
            user_settings.load_settings(), {"PREFERRED_INPUT_DEVICES": bom}
        )

    def test_booleano_nao_aceita_numero(self):
        # Em Python bool é subclasse de int, então a checagem ingênua
        # (isinstance(x, int)) aceitaria 1/0 — e o contrário, aceitar
        # True onde se espera número, também. Confere os dois sentidos.
        self.escrever({"DICTATION_SOUNDS_ENABLED": 1})
        self.assertEqual(user_settings.load_settings(), {})
        self.escrever({"DICTATION_SOUNDS_ENABLED": False})
        self.assertEqual(
            user_settings.load_settings(), {"DICTATION_SOUNDS_ENABLED": False}
        )


class EscritaTest(SettingsTestCase):
    def test_grava_e_le_de_volta(self):
        self.assertTrue(user_settings.save_settings({"NTFY_TOPIC": "visper-xyz"}))
        self.assertEqual(
            user_settings.load_settings(), {"NTFY_TOPIC": "visper-xyz"}
        )

    def test_grava_mesclando_com_o_que_ja_existia(self):
        user_settings.save_settings({"NTFY_TOPIC": "visper-1"})
        user_settings.save_settings({"WAKE_WORD": "Íris"})
        self.assertEqual(
            user_settings.load_settings(),
            {"NTFY_TOPIC": "visper-1", "WAKE_WORD": "Íris"},
        )

    def test_none_remove_a_chave(self):
        user_settings.save_settings({"WAKE_WORD": "Íris"})
        user_settings.save_settings({"WAKE_WORD": None})
        self.assertEqual(user_settings.load_settings(), {})

    def test_cria_a_pasta_se_nao_existir(self):
        fundo = Path(self._tmp.name) / "a" / "b" / "settings.json"
        os.environ[user_settings.ENV_OVERRIDE] = str(fundo)
        self.assertTrue(user_settings.save_settings({"WAKE_WORD": "Íris"}))
        self.assertTrue(fundo.exists())

    def test_arquivo_so_e_legivel_pela_dona(self):
        # O arquivo guarda o tópico do ntfy, que é a senha que protege o
        # Mac de automação remota — não deve ficar legível pra outros
        # usuários da máquina.
        user_settings.save_settings({"NTFY_TOPIC": "visper-secreto"})
        self.assertEqual(self.path.stat().st_mode & 0o077, 0)

    def test_valor_invalido_nao_e_gravado(self):
        user_settings.save_settings({"WAKE_WORD": ["lista", "errada"]})
        self.assertEqual(user_settings.load_settings(), {})


class SobreposicaoTest(SettingsTestCase):
    def test_sobrepoe_so_o_que_ja_existe_no_namespace(self):
        ns = {"WAKE_WORD": "vIsper", "DEFAULT_AI": "claude"}
        self.escrever({"WAKE_WORD": "Vésper", "NTFY_TOPIC": "visper-abc"})
        aplicadas = user_settings.apply_overrides(ns)
        self.assertEqual(ns["WAKE_WORD"], "Vésper")
        # NTFY_TOPIC não existia no namespace, então não foi criado.
        self.assertNotIn("NTFY_TOPIC", ns)
        self.assertEqual(aplicadas, ["WAKE_WORD"])

    def test_sem_arquivo_nao_muda_nada(self):
        ns = {"WAKE_WORD": "vIsper"}
        self.assertEqual(user_settings.apply_overrides(ns), [])
        self.assertEqual(ns["WAKE_WORD"], "vIsper")

    def test_default_ai_orfao_volta_pra_uma_ia_existente(self):
        # Rede de segurança: se o settings.json trocar AI_TRIGGERS e
        # deixar DEFAULT_AI apontando pra uma IA que não existe mais, o
        # app abriria e nunca conseguiria abrir a IA padrão — falha
        # calada, das piores de diagnosticar.
        ns = {"AI_TRIGGERS": {"claude": ["claude"]}, "DEFAULT_AI": "claude"}
        self.escrever({"AI_TRIGGERS": {"gemini": ["gemini"]}})
        user_settings.apply_overrides(ns)
        self.assertEqual(ns["DEFAULT_AI"], "gemini")

    def test_default_ai_valido_e_preservado(self):
        ns = {"AI_TRIGGERS": {"claude": ["claude"]}, "DEFAULT_AI": "claude"}
        self.escrever(
            {"AI_TRIGGERS": {"claude": ["claude"], "gemini": ["gemini"]}}
        )
        user_settings.apply_overrides(ns)
        self.assertEqual(ns["DEFAULT_AI"], "claude")


class ConfigIntegradoTest(SettingsTestCase):
    def test_config_reflete_o_settings_json(self):
        # Ponta a ponta: quem faz `import config` recebe o valor já
        # sobreposto, sem saber que houve sobreposição — é o contrato
        # que permitiu não mexer em nenhum outro módulo.
        import importlib

        self.escrever({"WAKE_WORD": "Sussurro", "DEFAULT_AI": "gemini"})
        import config

        importlib.reload(config)
        try:
            self.assertEqual(config.WAKE_WORD, "Sussurro")
            self.assertEqual(config.DEFAULT_AI, "gemini")
            self.assertEqual(config.OVERRIDDEN_KEYS, ["DEFAULT_AI", "WAKE_WORD"])
        finally:
            # Recarrega sem a env var pra não contaminar outros testes —
            # config é módulo global e fica em sys.modules.
            os.environ.pop(user_settings.ENV_OVERRIDE, None)
            importlib.reload(config)


if __name__ == "__main__":
    unittest.main()


class FuzzyThresholdTest(SettingsTestCase):
    def test_aceita_fracao_valida(self):
        self.escrever({"FUZZY_MATCH_THRESHOLD": 0.8})
        self.assertEqual(
            user_settings.load_settings(), {"FUZZY_MATCH_THRESHOLD": 0.8}
        )

    def test_um_ponto_zero_desliga_a_tolerancia_e_e_valido(self):
        self.escrever({"FUZZY_MATCH_THRESHOLD": 1.0})
        self.assertEqual(
            user_settings.load_settings(), {"FUZZY_MATCH_THRESHOLD": 1.0}
        )

    def test_rejeita_fora_da_faixa_booleano_e_texto(self):
        # Abaixo de 0.5 qualquer palavra casa com qualquer outra — isso
        # não é configuração, é o app abrindo IA por conta própria.
        for ruim in [0.3, 1.5, True, "0.8", None]:
            with self.subTest(valor=ruim):
                self.escrever({"FUZZY_MATCH_THRESHOLD": ruim})
                self.assertEqual(user_settings.load_settings(), {})


class TranscriptionLanguagesTest(SettingsTestCase):
    """
    TRANSCRIPTION_LANGUAGES: lista dos idiomas que a pessoa fala — a
    resposta direta pra "só funciona em inglês", que é o Whisper sendo
    pouco confiável detectando idioma em áudio CURTO (ver comentário
    completo em config.py).
    """

    def test_aceita_um_idioma(self):
        self.escrever({"TRANSCRIPTION_LANGUAGES": ["pt"]})
        self.assertEqual(
            user_settings.load_settings(), {"TRANSCRIPTION_LANGUAGES": ["pt"]}
        )

    def test_aceita_varios_idiomas(self):
        self.escrever({"TRANSCRIPTION_LANGUAGES": ["pt", "en"]})
        self.assertEqual(
            user_settings.load_settings(), {"TRANSCRIPTION_LANGUAGES": ["pt", "en"]}
        )

    def test_lista_vazia_e_valida_significa_sem_restricao(self):
        self.escrever({"TRANSCRIPTION_LANGUAGES": []})
        self.assertEqual(
            user_settings.load_settings(), {"TRANSCRIPTION_LANGUAGES": []}
        )

    def test_rejeita_tipo_errado(self):
        for ruim in ["pt", 7, None, ["pt", 7], [True]]:
            with self.subTest(valor=ruim):
                self.escrever({"TRANSCRIPTION_LANGUAGES": ruim})
                self.assertEqual(user_settings.load_settings(), {})

    def test_limiar_de_confianca_validado_como_fracao(self):
        self.escrever({"LANGUAGE_CONFIDENCE_THRESHOLD": 0.7})
        self.assertEqual(
            user_settings.load_settings(), {"LANGUAGE_CONFIDENCE_THRESHOLD": 0.7}
        )
        for ruim in [-0.1, 1.5, True, "0.7"]:
            with self.subTest(valor=ruim):
                self.escrever({"LANGUAGE_CONFIDENCE_THRESHOLD": ruim})
                self.assertEqual(user_settings.load_settings(), {})

    def test_config_le_os_idiomas_sobrepostos(self):
        import importlib

        self.escrever({"TRANSCRIPTION_LANGUAGES": ["es"]})
        import config

        importlib.reload(config)
        try:
            self.assertEqual(config.TRANSCRIPTION_LANGUAGES, ["es"])
        finally:
            os.environ.pop(user_settings.ENV_OVERRIDE, None)
            importlib.reload(config)

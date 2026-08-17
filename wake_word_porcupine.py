"""
wake_word_porcupine.py — detector de wake word acústico de verdade
(reconhece o SOM da palavra, não uma transcrição escrita), usando o
Porcupine (Picovoice). Sem PORCUPINE_ACCESS_KEY e
PORCUPINE_KEYWORD_PATH configurados em config.py, essa peça fica
desligada (`.enabled == False`) e o app continua no modo atual
(Whisper contínuo + procura a wake word no texto) — nada quebra.

Setup, do lado da Valeta (não dá pra automatizar daqui):
  1. Criar conta grátis em console.picovoice.ai
  2. Pegar o AccessKey da conta (no painel, não precisa treinar nada
     pra isso)
  3. Na seção Porcupine, digitar a wake word e treinar
  4. Baixar o arquivo .ppn gerado pra macOS
  5. Colocar os dois valores em config.py: PORCUPINE_ACCESS_KEY e
     PORCUPINE_KEYWORD_PATH (caminho do .ppn)

NUNCA TESTADO CONTRA O MOTOR DE VERDADE: escrito contra a API real do
pacote `pvporcupine` (instalei e conferi as assinaturas de
pvporcupine.create/.process/.sample_rate/.frame_length antes de
escrever isso — não é de memória). Mas sem AccessKey nem arquivo
.ppn não dá pra criar uma instância real nem testar detecção com
áudio de verdade. O que ESTÁ testado (test_wake_word_porcupine.py) é
a parte que dá pra isolar sem esses dois: liga/desliga corretamente
conforme a config, e o mapeamento do resultado do process() pra
True/False.

INTEGRAÇÃO NA main.py AINDA PENDENTE, de propósito: hoje main.py
escuta de um jeito só (Whisper contínuo, chunks de 4s). Ligar isso
de verdade significa dois loops de áudio rodando ao mesmo tempo — o
Porcupine (frames pequenos e fixos, contínuo, barato) pra saber SE
tem wake word, e o Whisper (ativado só depois da detecção) pra saber
O QUE foi dito. É mudança de arquitetura de concorrência, não só
plugar um módulo — fazer isso sem conseguir testar com mic e
AccessKey de verdade é mais risco do que vale a pena inventar aqui
às cegas. Primeira tarefa de verdade pra isso no Claude Code, com
mic real na mão.
"""

try:
    import pvporcupine
except ImportError:
    pvporcupine = None


class PorcupineWakeWordDetector:
    def __init__(self, access_key: str, keyword_path: str, sensitivity: float = 0.5):
        self.access_key = access_key
        self.keyword_path = keyword_path
        self.sensitivity = sensitivity
        self._porcupine = None

    @property
    def enabled(self) -> bool:
        """False se faltar chave/arquivo (ou o pacote não estiver
        instalado) — nesse caso quem chama deve continuar no modo
        Whisper contínuo, nunca travar por causa disso."""
        return bool(self.access_key and self.keyword_path and pvporcupine is not None)

    def start(self):
        if not self.enabled:
            raise RuntimeError(
                "Porcupine não configurado — defina PORCUPINE_ACCESS_KEY e "
                "PORCUPINE_KEYWORD_PATH em config.py antes de chamar start(), "
                "ou confira se 'pip install pvporcupine' rodou certo."
            )
        self._porcupine = pvporcupine.create(
            access_key=self.access_key,
            keyword_paths=[self.keyword_path],
            sensitivities=[self.sensitivity],
        )
        return self

    @property
    def sample_rate(self) -> int:
        return self._porcupine.sample_rate

    @property
    def frame_length(self) -> int:
        return self._porcupine.frame_length

    def process_frame(self, pcm_int16) -> bool:
        """
        pcm_int16: um frame com exatamente `frame_length` amostras
        int16 (16-bit, mono, sample_rate = self.sample_rate — o
        Porcupine é rígido quanto a isso). Retorna True se a wake
        word foi detectada nesse frame.
        """
        return self._porcupine.process(pcm_int16) >= 0

    def stop(self):
        if self._porcupine is not None:
            self._porcupine.delete()
            self._porcupine = None

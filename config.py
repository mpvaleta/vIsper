"""
config.py — os PADRÕES de tudo que você provavelmente vai querer
ajustar: a palavra de ativação, qual IA abre por padrão, os apelidos
de cada IA (em quantos idiomas quiser), e as frases que sinalizam
"terminei/próximo".

═══════════════════════════════════════════════════════════════════
NÃO COLOQUE NADA PESSOAL AQUI. Este arquivo é VERSIONADO num
repositório PÚBLICO — o que você escrever nele pode acabar publicado
num `git push`. Isso vale especialmente pro tópico do ntfy e pra
chave do Porcupine (ver os comentários deles lá embaixo).

Sua configuração pessoal mora fora do repositório, em:
    ~/Library/Application Support/vIsper/settings.json

A forma mais fácil de criar esse arquivo é rodar:
    python3 setup_visper.py

O que estiver lá sobrepõe o que está aqui (ver user_settings.py, e a
chamada de apply_overrides() no fim deste arquivo). Vantagem além da
segurança: atualizar o vIsper (`git pull`) nunca dá conflito com o
que você configurou, e dá pra mandar o vIsper pra outra pessoa sem
mandar junto a sua configuração.
═══════════════════════════════════════════════════════════════════
"""

from user_settings import apply_overrides

# Palavra (ou frase curta) que ativa o vIsper. Se ela for uma palavra
# inventada (tipo "vIsper" mesmo), o reconhecimento por Whisper pode
# errar a grafia — ver nota no README sobre trocar pro Porcupine,
# que reconhece o SOM da palavra em vez de tentar escrever ela.
WAKE_WORD = "vIsper"

# Se você disser só a wake word e mais nada reconhecível, essa é a IA
# que abre. Troque pra "chatgpt", "claude_code" etc. — tem que ser uma
# das chaves de AI_TRIGGERS abaixo.
DEFAULT_AI = "claude"

# Cada IA tem uma lista de apelidos — em qualquer idioma que você
# queira usar pra chamá-la. O primeiro apelido que aparecer no que
# você falou depois da wake word decide qual IA abre.
AI_TRIGGERS = {
    "claude": ["claude"],
    "claude_code": ["claude code", "claude código"],
    "chatgpt": ["chatgpt", "chat gpt"],
    "perplexity": ["perplexity"],
    "gemini": ["gemini"],
}

# Além de repetir a própria wake word, essas palavras também
# sinalizam "manda ver" durante o ditado — não precisa decorar uma
# frase específica. Escolhidas emprestando o vocabulário de rádio
# ("câmbio"/"over" = "terminei de falar, sua vez") porque o sentido
# encaixa exatamente com o que a ação faz, E — mais importante pra
# funcionar bem — nenhuma das duas é comum o bastante pra aparecer
# sem querer no meio do que você tá ditando (ao contrário de
# "manda"/"send", "pronto"/"done", que são palavras do dia a dia
# demais pra isso). Casam como PALAVRA INTEIRA (ver text_utils.py),
# então "over" não confunde com "however"/"moreover"/"cover".
CLOSE_TRIGGERS = ["câmbio", "over"]

# Tópico do ntfy (https://ntfy.sh) que o app de iPhone usa pra mandar
# comando pro Mac de qualquer lugar (não só na mesma Wi-Fi) — ver
# relay_listener.py.
#
# ATENÇÃO — SEGURANÇA, e aqui é a sério: tópicos do ntfy.sh não têm
# senha. O NOME do tópico é a única coisa que impede qualquer pessoa
# do mundo de mandar comando de verdade pro seu Mac (abrir apps, colar
# texto, apertar Enter). Ou seja: é uma senha.
#
# Por isso ele NÃO se configura aqui — este arquivo vai pro GitHub.
# Rode `python3 setup_visper.py`, que sorteia um tópico aleatório e
# guarda em ~/Library/Application Support/vIsper/settings.json, fora
# do repositório.
#
# Deixe em branco ("") pra manter o relay desligado e usar só o mic
# local. Se algum dia você desconfiar que o tópico vazou, rode o
# setup_visper.py de novo pra sortear outro — é instantâneo, e o
# antigo deixa de valer.
NTFY_TOPIC = ""

# Idioma que o transcritor deve assumir. `None` = detectar sozinho a
# cada trecho de ~4s (funciona, mas Whisper é conhecido por ser pouco
# confiável detectando idioma em ÁUDIO CURTO — com poucos segundos de
# fala, o modelo tende a "chutar" inglês com mais frequência do que
# deveria, mesmo ouvindo outra língua com clareza; é limitação
# documentada do próprio modelo, não bug daqui). Se você fala
# predominantemente um idioma, force ele aqui — pula a detecção
# incerta por completo, então funciona melhor E mais rápido:
#   "pt" — português
#   "en" — inglês
# Lista completa de códigos: https://github.com/openai/whisper#available-models-and-languages
# `python3 setup_visper.py` pergunta isso.
TRANSCRIPTION_LANGUAGE = None

# Tolerância a erro de transcrição na ABERTURA de comando (wake word e
# nome da IA). O Whisper erra a grafia de palavra inventada com
# frequência — "vIsper" vira "whisper"/"vesper", "claude" falado em
# português vira "cloud"/"clode" — e antes disso cada erro desses fazia
# o comando falhar CALADO, como se o app fosse surdo.
#
# 0.72 foi MEDIDO, não chutado: pega todas as variantes reais
# ("whisper" 0.77, "cloud" 0.73, "claudio" 0.77) e rejeita as palavras
# de ditado mais parecidas ("dispersar" 0.67, "sempre" 0.50). Suba pra
# 1.0 pra exigir casamento exato (desliga a tolerância); desça com
# cuidado — abaixo de ~0.70 palavras comuns começam a colar.
#
# Só vale pra ABRIR. O FECHAMENTO ("câmbio"/"over"/wake word durante o
# ditado) é sempre exato: fechar por engano manda a mensagem pela
# metade, que é destrutivo; abrir por engano só abre uma aba à toa.
FUZZY_MATCH_THRESHOLD = 0.72

# IAs que o relay do iPhone NÃO pode abrir, mesmo com o tópico certo.
#
# Por que isso existe: abrir "claude_code" roda um AppleScript que abre
# o Terminal e DIGITA dentro dele. Pelo microfone local isso é ótimo —
# você está na frente da máquina. Vindo do ntfy é outra coisa: quem
# souber o tópico deixa de "conseguir digitar num chat de IA" e passa a
# "conseguir digitar num terminal", que é execução de comando. A
# diferença de gravidade entre as duas é grande demais pra deixar as
# duas no mesmo balde.
#
# Isso não substitui manter o tópico secreto — é a segunda tranca, pro
# caso da primeira falhar. Esvazie a lista ([]) se quiser mesmo poder
# abrir o Terminal pelo iPhone.
RELAY_BLOCKED_AIS = ["claude_code"]

# Tamanho máximo (caracteres) de uma mensagem vinda do relay. Uma
# mensagem gigante seria colada inteira no chat da IA; o ntfy aceita
# corpos bem maiores do que qualquer ditado real precisa.
RELAY_MAX_MESSAGE_CHARS = 4000

# Motor de wake-word de verdade (opcional) — reconhece o SOM da
# palavra em vez de procurar ela numa transcrição escrita. Ver
# wake_word_porcupine.py e o passo a passo no README pra conseguir
# esses dois valores. Deixe os dois em branco pra continuar no modo
# atual (Whisper contínuo).
#
# A AccessKey é credencial da SUA conta na Picovoice — mesma regra do
# NTFY_TOPIC acima: configure pelo `python3 setup_visper.py`, não aqui,
# senão ela vai parar no GitHub.
PORCUPINE_ACCESS_KEY = ""
PORCUPINE_KEYWORD_PATH = ""

# Dispositivos de ENTRADA preferidos, em ordem de prioridade — usado
# por audio_input.guess_preferred_device() pra escolher o mic sozinho
# ao abrir o app (e de novo, fresco, toda vez que "Iniciar escuta" é
# clicado sem nenhum microfone escolhido manualmente no menu).
#
# Cada item é um grupo: {"keywords": [...], "bluetooth": bool}.
#   - "keywords": palavras (minúsculas) procuradas como SUBSTRING no
#     nome que o macOS dá ao dispositivo — não por palavra inteira
#     (ao contrário de text_utils.contains_word, que serve pra
#     transcrição falada, não nome de hardware). Ex.: "xm5" bate com
#     "WH-1000XM5" e com "Marcos's WH-1000XM5" igual.
#   - "bluetooth": True avisa o resto do código (main.py) que esse
#     dispositivo é um fone sem fio — o Mac derruba a qualidade do
#     ÁUDIO DO SISTEMA INTEIRO (não só da gravação) pra mono/telefone
#     (perfil HFP/HSP) enquanto o microfone dele estiver aberto. Ver
#     aviso completo no README ("Sobre usar fone de ouvido").
#
# O PRIMEIRO GRUPO que bater com algum dispositivo conectado ganha —
# por isso o DJI Mic vem antes do Sony aqui: é um mic USB dedicado, com
# qualidade melhor e sem o efeito colateral acima. Se você preferir
# que o fone ganhe do DJI quando os dois estiverem disponíveis, é só
# reordenar a lista. Pra adicionar seu próprio fone/mic, acrescente um
# grupo nesta lista — rode `python3 doctor.py` (ver check_input_device)
# ou o item "Escolher microfone" no menu pra ver o nome exato que o seu
# macOS usa antes de escrever o keyword.
PREFERRED_INPUT_DEVICES = [
    # Mesmas 3 keywords de sempre (era hardcoded em audio_input.py) —
    # "rx" sozinho fica solto de propósito, pra cobrir receiver que o
    # macOS lista só como "... RX" sem "DJI" nem "Wireless Microphone"
    # na frente.
    {"keywords": ["dji", "wireless microphone rx", "rx"], "bluetooth": False},
    {"keywords": ["wh-1000xm5", "wf-1000xm5", "xm5"], "bluetooth": True},
]

# Feedback sonoro (earcon) quando o ditado abre/fecha — toca um som já
# embutido no macOS (/System/Library/Sounds/*.aiff), sem precisar de
# nenhum arquivo extra. Fica mais útil ainda usando fone de ouvido: dá
# pra saber que abriu/mandou sem precisar olhar pra barra de menu (ex.:
# durante o treino). Nomes válidos, todos já vêm instalados: Basso,
# Blow, Bottle, Frog, Funk, Glass, Hero, Morse, Ping, Pop, Purr,
# Sosumi, Submarine, Tink.
DICTATION_SOUNDS_ENABLED = True
DICTATION_OPEN_SOUND = "Pop"    # toca quando o ditado ABRE (IA lançada, começou a ouvir)
DICTATION_SEND_SOUND = "Glass"  # toca quando o ditado FECHA com conteúdo (colou + apertou Enter)


def transcription_hotwords() -> str:
    """
    O vocabulário de comando inteiro, numa string só, pro transcritor
    PRIORIZAR essas palavras na hora de decidir o que ouviu — parâmetro
    `hotwords` do faster-whisper (existe na 1.0.3 do requirements.txt;
    conferido no fonte da wheel baixada da PyPI, não de memória).

    É a outra metade da melhoria de detecção, complementar ao
    FUZZY_MATCH_THRESHOLD acima: o fuzzy conserta a grafia DEPOIS que o
    Whisper errou; isto faz o Whisper errar MENOS — com "vIsper" na
    lista de prioridade, a chance de ele escrever "whisper" cai.

    É função (não constante) de propósito: lê os valores FINAIS, já com
    o settings.json aplicado — quem trocar a wake word ganha a
    priorização da palavra nova sem mexer em nada.
    """
    words = [WAKE_WORD]
    for triggers in AI_TRIGGERS.values():
        words.extend(triggers)
    words.extend(CLOSE_TRIGGERS)
    # dict.fromkeys: dedup preservando a ordem (wake word primeiro).
    return ", ".join(dict.fromkeys(w for w in words if w))


# ---------------------------------------------------------------------
# Sobreposição pela configuração PESSOAL — precisa ser a última linha
# do arquivo, senão sobrepõe valores que ainda nem foram definidos.
#
# Tudo acima é PADRÃO; o que estiver em
# ~/Library/Application Support/vIsper/settings.json ganha. Arquivo
# faltando ou quebrado não faz nada acontecer (fica só no padrão) —
# ver user_settings.py pro raciocínio completo.
#
# OVERRIDDEN_KEYS é só informativo: o doctor.py mostra essa lista, o
# que transforma "meu tópico não funciona" em "ah, ele nem estava
# sendo lido".
# ---------------------------------------------------------------------
OVERRIDDEN_KEYS = apply_overrides(globals())

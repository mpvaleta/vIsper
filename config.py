"""
config.py — tudo que você provavelmente vai querer ajustar sem mexer
no resto do código: a palavra de ativação, qual IA abre por padrão,
os apelidos de cada IA (em quantos idiomas quiser), e as frases que
sinalizam "terminei/próximo".

Edite essas listas à vontade — não precisa reiniciar nada além de
rodar o app de novo.
"""

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
# ATENÇÃO — SEGURANÇA: tópicos do ntfy.sh não têm senha por padrão.
# Qualquer um que adivinhar esse nome pode mandar comando de verdade
# pro seu Mac (abrir apps, colar texto, apertar Enter). Troque o
# placeholder abaixo por uma string longa e aleatória — por exemplo,
# rode isto no terminal e cole o resultado:
#   python3 -c "import secrets; print('visper-' + secrets.token_urlsafe(24))"
# Deixe em branco ("") pra desligar o relay e usar só o mic local.
NTFY_TOPIC = ""

# Motor de wake-word de verdade (opcional) — reconhece o SOM da
# palavra em vez de procurar ela numa transcrição escrita. Ver
# wake_word_porcupine.py e o passo a passo no README pra conseguir
# esses dois valores. Deixe os dois em branco pra continuar no modo
# atual (Whisper contínuo).
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

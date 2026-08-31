"""
text_utils.py — normalização e correspondência de texto compartilhada
entre command_router.py e dictation.py. Existe pra não duplicar a
mesma lógica de "isso aparece como PALAVRA INTEIRA no texto, sem
acento, sem diferenciar maiúscula/minúscula" nos dois lugares.

Por que isso importa: comparar com "in" (substring simples) tem um
risco real — foi assim que "over" (ver dictation.py) acabaria casando
dentro de "however", "moreover", "discover", "cover", que são palavras
comuns o bastante pra aparecer em qualquer ditado em inglês. Casar só
como PALAVRA INTEIRA evita isso.
"""

import re
import unicodedata
from difflib import SequenceMatcher


def _is_edge_char(ch: str) -> bool:
    """
    True pra espaço em branco e pra QUALQUER pontuação/símbolo Unicode —
    usado pra aparar sobra de pontuação nas bordas de um trecho já
    isolado (ex.: o que vem depois da wake word). Existe porque o
    Whisper adiciona pontuação de frase com frequência mesmo em falas
    curtas (ex.: transcreve só a wake word como "vIsper." com ponto
    final) — sem aparar isso, um resto que deveria contar como "nada
    depois da wake word" sobra como "." (não-vazio) e o comando inteiro
    falha silenciosamente. Ver split_after_word().

    Testa por CATEGORIA Unicode em vez de uma lista fixa de caracteres
    ASCII (era `string.whitespace + string.punctuation`): o Whisper
    transcreve travessão, reticências e aspas curvas de VERDADE
    ("—", "…", "“”", "¿", "¡"), nenhum deles ASCII. Com a lista antiga,
    "vIsper—" deixava "—" sobrando como se fosse conteúdo e a wake word
    sozinha simplesmente não abria a IA padrão — o mesmo bug que o caso
    "vIsper." já tinha corrigido, só que pra pontuação não-ASCII.
    """
    return ch.isspace() or unicodedata.category(ch)[0] in ("P", "S")


def _strip_edges(text: str, left: bool = True, right: bool = True) -> str:
    """str.strip() consciente de Unicode — ver _is_edge_char()."""
    start, end = 0, len(text)
    if left:
        while start < end and _is_edge_char(text[start]):
            start += 1
    if right:
        while end > start and _is_edge_char(text[end - 1]):
            end -= 1
    return text[start:end]


def fold_accents(text: str) -> str:
    """Remove acentos (á→a, ç→c, ã→a...) pra comparação tolerante a
    erro de transcrição do Whisper com/sem acento — "câmbio" e
    "cambio" precisam contar como a mesma palavra."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _fold_with_index_map(text: str):
    """
    Dobra o texto (minúsculas + sem acento) devolvendo TAMBÉM um mapa
    que leva cada posição do texto DOBRADO de volta pra posição
    correspondente no texto ORIGINAL.

    POR QUE ISSO PRECISA EXISTIR (bug real, já corrigido aqui): as
    funções que preservam o texto original (split_before_any() e
    text_after_word()) acham o gatilho no texto dobrado e depois
    FATIAM o texto original com esse índice. Isso só funciona se dobrar
    preservar o comprimento caractere a caractere — o que NÃO é
    verdade. fold_accents() usa NFKD (decomposição de COMPATIBILIDADE),
    então "…" (U+2026, que o Whisper transcreve de verdade) vira "..."
    e cresce 2 caracteres; ligaduras tipo "ﬁ" viram "fi" e crescem 1.
    A partir daí todo índice fica deslocado e o texto colado no chat
    sai corrompido — por exemplo:
        split_before_any("Bom dia… over", ["over"])
          -> "Bom dia… ov"        (vazava o gatilho e comia conteúdo)
        text_after_word("vIsper… claude qual é a previsão", "claude")
          -> "ual é a previsão"   (comia os 2 primeiros caracteres)

    Dobrando CARACTERE A CARACTERE dá pra registrar, pra cada
    caractere produzido, de qual índice do original ele veio — aí o
    fatiamento volta a ser exato mesmo quando dobrar muda o tamanho.
    Um caractere pode produzir vários (…→...), um (á→a) ou nenhum (um
    acento combinante solto, em texto já decomposto/NFD).

    Retorna (texto_dobrado, mapa). O mapa tem len(dobrado)+1 entradas:
    a última é len(text), pra um match que termina no fim da string
    também ter pra onde apontar.
    """
    pieces = []
    index_map = []
    for original_index, ch in enumerate(text):
        piece = fold_accents(ch.lower())
        pieces.append(piece)
        index_map.extend([original_index] * len(piece))
    index_map.append(len(text))
    return "".join(pieces), index_map


def _fold_for_match(text: str) -> str:
    """Mesmo resultado de _fold_with_index_map()[0], sem montar o mapa —
    pra quem só compara e não precisa fatiar o original de volta."""
    return "".join(fold_accents(ch.lower()) for ch in text)


def _word_pattern(*words) -> str:
    """
    Regex que casa qualquer uma das `words` como PALAVRA INTEIRA.

    Usa lookaround (?<!\\w)/(?!\\w) em vez de \\b: \\b é definido em
    relação a caractere de palavra, então um gatilho que COMEÇA ou
    TERMINA com pontuação (config.AI_TRIGGERS é editável à mão — nada
    impede um apelido tipo "gpt-4o+" amanhã) inverte o sentido do \\b e
    o apelido simplesmente nunca casa. O lookaround exprime direto o
    que a gente quer: "não pode ter caractere de palavra colado nas
    bordas". Pra gatilhos que só têm letras — todos os de hoje — o
    comportamento é idêntico ao de \\b.
    """
    alternatives = "|".join(re.escape(w) for w in words)
    return r"(?<!\w)(?:" + alternatives + r")(?!\w)"


def contains_word(haystack: str, word: str) -> bool:
    """
    True se `word` aparece em `haystack` como palavra (ou frase)
    inteira — não como substring dentro de outra palavra maior.
    Ignora maiúscula/minúscula e acento dos dois lados. `word` pode
    ter espaço dentro (frases tipo "claude code" funcionam igual).
    """
    return find_word(haystack, word) is not None


def find_word(haystack: str, word: str):
    """
    Posição da primeira ocorrência de `word` como palavra inteira em
    `haystack` (medida no texto DOBRADO, ver _fold_for_match()), ou
    None se não aparecer.

    Existe pro command_router.py conseguir escolher a IA pelo apelido
    que aparece PRIMEIRO na fala, não pelo mais comprido — só saber
    "apareceu ou não" (contains_word) não dá pra desempatar isso.
    Comparar posições só faz sentido entre chamadas com o MESMO
    `haystack`, que é exatamente como o router usa.
    """
    if not word:
        return None
    match = re.search(
        _word_pattern(_fold_for_match(word)), _fold_for_match(haystack)
    )
    return match.start() if match else None


def starts_with_word(haystack: str, word: str) -> bool:
    """
    True se `haystack` COMEÇA com `word` como palavra (ou frase)
    inteira. Ignora maiúscula/minúscula, acento e pontuação/espaço
    antes da palavra.

    Diferente de contains_word() de propósito, e a diferença é o que
    torna o cancelamento seguro: "cancela" pode aparecer em qualquer
    lugar de uma frase ditada de verdade ("preciso cancelar a
    reserva"), então só ADJACÊNCIA à wake word — "vIsper, cancela",
    nessa ordem, coladas — distingue um comando de uma frase. Ver
    dictation._is_cancel() e config.CANCEL_TRIGGERS.
    """
    if not word:
        return False
    inicio = _strip_edges(_fold_for_match(haystack), right=False)
    return re.match(_word_pattern(_fold_for_match(word)), inicio) is not None


def split_after_word(haystack: str, word: str) -> str:
    """
    Retorna o que vem depois da PRIMEIRA ocorrência de `word` como
    palavra inteira em `haystack`, ou string vazia se não achar (ou se
    só sobrar pontuação — ver _EDGE_CHARS).

    O retorno já vem sem acento e em minúsculas (mesmo tratamento do
    `haystack`) — funciona bem porque quem usa isso só compara contra
    outros gatilhos depois, nunca mostra esse texto pro usuário.
    """
    if not word:
        return ""
    haystack_folded = _fold_for_match(haystack)
    match = re.search(_word_pattern(_fold_for_match(word)), haystack_folded)
    if not match:
        return ""
    return _strip_edges(haystack_folded[match.end():])


def text_after_word(haystack: str, word: str) -> str:
    """
    Como split_after_word(), mas preserva CAPITALIZAÇÃO, ACENTO e
    PONTUAÇÃO REAL originais de `haystack` — usado quando o resultado
    pode virar conteúdo real de ditado (ex.: command_router.py, pro
    caso "vIsper claude qual é a previsão do tempo" tudo numa
    respiração só: o que sobra depois de "claude" não pode ser jogado
    fora nem voltar tudo minúsculo/sem acento/sem pontuação).
    split_after_word() continua sendo a certa pra comparar contra
    outro gatilho (nunca mostrado pra ninguém, pode aparar pontuação à
    vontade); esta é a irmã que preserva o texto pra valer.

    As duas bordas são tratadas DIFERENTE de propósito:
      - Borda ESQUERDA (logo depois de `word`): apara espaço E
        pontuação (ex.: "claude," "claude:" "claude —") — o que vem
        colado ali é sempre artefato de como a palavra foi dita, nunca
        conteúdo de verdade.
      - Borda DIREITA: apara só espaço. Pontuação ali costuma ser o
        FIM de uma frase real ("qual é a previsão do tempo hoje?") —
        tirar o "?" mudaria o sentido do que a pessoa disse.

    Retorna "" se `word` não aparecer como palavra inteira.
    """
    if not word:
        return ""
    haystack_folded, index_map = _fold_with_index_map(haystack)
    match = re.search(_word_pattern(_fold_for_match(word)), haystack_folded)
    if not match:
        return ""
    # index_map traduz a posição no texto dobrado pra posição no texto
    # ORIGINAL — dobrar pode mudar o comprimento (ver
    # _fold_with_index_map()), então fatiar o original com o índice cru
    # do match comia/deslocava caracteres do conteúdo de verdade.
    return _strip_edges(haystack[index_map[match.end()]:], right=False).rstrip()


def _tokens_with_spans(haystack: str):
    """
    Quebra `haystack` em palavras, devolvendo cada uma já DOBRADA
    (minúscula/sem acento) e aparada de pontuação nas bordas, junto com
    o intervalo [início, fim) que ela ocupa no texto ORIGINAL.

    A tradução dobrado→original usa _fold_with_index_map() — regra da
    casa: qualquer função que ache posição no texto dobrado e fatie o
    original TEM que passar pelo mapa, porque dobrar não preserva
    comprimento ("…"→"...", "ﬁ"→"fi"; ver a docstring de lá, com os
    bugs reais que isso causou).

    Retorna lista de (palavra_dobrada, inicio_original, fim_original).
    """
    folded, index_map = _fold_with_index_map(haystack)
    tokens = []
    i, n = 0, len(folded)
    while i < n:
        while i < n and folded[i].isspace():
            i += 1
        j = i
        while j < n and not folded[j].isspace():
            j += 1
        if j > i:
            # Apara pontuação DENTRO do token ("claude," → "claude"),
            # mantendo o intervalo apontando só pro miolo que sobrou.
            a, b = i, j
            while a < b and _is_edge_char(folded[a]):
                a += 1
            while b > a and _is_edge_char(folded[b - 1]):
                b -= 1
            if b > a:
                tokens.append((folded[a:b], index_map[a], index_map[b]))
        i = j
    return tokens


# Palavras mais curtas que isso nunca casam por aproximação — num token
# de 3 letras, uma única letra diferente já é um terço da palavra, e a
# chance de colisão com palavra comum do dia a dia fica alta demais.
_MIN_FUZZY_LEN = 4


def find_trigger_span(haystack: str, trigger: str, threshold: float = 1.0):
    """
    Procura `trigger` (1+ palavras) em `haystack` e devolve
    (início, fim, ratio) — intervalo no texto ORIGINAL — ou None.

    Com threshold=1.0 (padrão) o casamento é EXATO por palavra inteira,
    como contains_word()/find_word(). Abaixo de 1.0, uma palavra
    PARECIDA o bastante também casa (difflib.SequenceMatcher), o que
    existe por um motivo concreto: a wake word padrão ("vIsper") é uma
    palavra inventada e o Whisper transcreve errado com frequência —
    "whisper" (ratio 0.77), "vesper" (0.83) —, e "claude" falado em
    português vira "cloud"/"clode" (0.73). Antes disso, cada uma dessas
    transcrições fazia o comando falhar SILENCIOSAMENTE: o app parecia
    surdo, que é a pior primeira impressão possível. Os limiares foram
    MEDIDOS (não chutados) contra variantes reais e contra as palavras
    de ditado mais próximas — "dispersar" vs "visper" dá 0.67, então
    0.72 separa os dois grupos com folga dos dois lados.

    QUEM pode usar aproximação é decisão de quem chama, e a regra do
    projeto é assimétrica de propósito (ver command_router/dictation):
    ABERTURA usa fuzzy (falso positivo = abre uma aba à toa, chato mas
    recuperável; falso negativo = app parece morto), FECHAMENTO nunca
    usa (falso positivo = manda a mensagem pela metade, destrutivo).

    Empate/ordem: devolve a ocorrência mais À ESQUERDA que atinja o
    threshold — consistente com a regra "posição primeiro" do
    command_router. Num mesmo ponto do texto, exato ganha de
    aproximado (é testado antes).
    """
    if not trigger:
        return None
    trigger_words = _fold_for_match(trigger).split()
    if not trigger_words:
        return None

    tokens = _tokens_with_spans(haystack)
    window = len(trigger_words)
    allow_fuzzy = threshold < 1.0

    for i in range(len(tokens) - window + 1):
        start, end = tokens[i][1], tokens[i + window - 1][2]
        # Compara PALAVRA POR PALAVRA, e o resultado da janela é o do
        # ELO MAIS FRACO (min), não a média nem o ratio da janela
        # emendada. O motivo é um bug que a versão emendada tinha de
        # verdade: em "vIsper claude não esqueça...", a janela
        # "claude nao" comparada inteira contra "claude code" dava 0.76
        # — o "claude" compartilhado dominava a conta e o "não" pegava
        # carona, abrindo o Claude Code (e comendo o "não" do
        # conteúdo). Palavra a palavra, "nao"×"code" reprova sozinho e
        # a janela morre, como deve.
        worst = 1.0
        for tok, trig_word in zip(
            (t[0] for t in tokens[i : i + window]), trigger_words
        ):
            if tok == trig_word:
                continue
            if (
                not allow_fuzzy
                or len(tok) < _MIN_FUZZY_LEN
                or len(trig_word) < _MIN_FUZZY_LEN
            ):
                worst = 0.0
                break
            ratio = SequenceMatcher(None, tok, trig_word).ratio()
            if ratio < threshold:
                worst = 0.0
                break
            worst = min(worst, ratio)
        # worst == 0.0 quer dizer "alguma palavra reprovou" (o break
        # acima); qualquer outra coisa é uma janela válida — cada par
        # já passou pelo threshold individualmente.
        if worst > 0.0:
            return start, end, worst
    return None


def trim_for_decision(text: str) -> str:
    """
    Prepara um resto de texto pra DECISÃO (nunca exibido): dobra e
    apara espaço/pontuação das duas bordas — mesma regra de
    split_after_word(). É o que responde "sobrou alguma coisa de
    verdade depois da wake word?" sem que um "." ou "—" solto conte
    como conteúdo.
    """
    return _strip_edges(_fold_for_match(text))


def trim_for_content(text: str) -> str:
    """
    Prepara um resto de texto pra virar CONTEÚDO real de ditado:
    preserva capitalização/acento/pontuação e apara com a MESMA
    assimetria de text_after_word() — pontuação só na borda esquerda
    (artefato de como a palavra anterior foi dita), espaço apenas na
    direita (um "?" no fim é fim de frase real da pessoa, não sobra).
    """
    return _strip_edges(text, right=False).rstrip()


def strip_trailing_word(haystack: str, words) -> str:
    """
    Se `haystack` TERMINA com uma das `words` (casada como palavra ou
    frase inteira, sem acento, sem diferenciar maiúscula/minúscula),
    devolve tudo ANTES dessa ocorrência final. Senão devolve
    `haystack` só com espaço aparado nas bordas.

    Existe pra dictation.DictationSession.handle_complete(): canais
    que entregam a mensagem já COMPLETA (o relay do iPhone) grudam um
    marcador fixo tipo "over" no FIM de toda mensagem, sempre, só pra
    sinalizar "isto é tudo" — não é o mesmo caso de split_before_any(),
    que acha a PRIMEIRA ocorrência em qualquer lugar do texto (certo
    pra um transcript de mic ainda podendo trazer o gatilho colado no
    meio). Se essa função usasse a mesma busca "em qualquer lugar", um
    conteúdo que legitimamente contivesse "over"/"câmbio" ANTES do
    marcador final seria cortado ali no meio — exatamente o bug que
    handle_complete() existe pra evitar. Casando só a partir do FIM,
    uma frase como "vamos discutir isso, over e out" (conteúdo real
    termina com "over" seguido de mais palavras, aí vem o marcador de
    verdade) preserva o "over" do meio e remove só o marcador colado no
    fim; e "let's talk this over" + marcador vira "let's talk this
    over over" -> remove só o ÚLTIMO, devolvendo "let's talk this
    over" — o "over" de verdade da frase sobrevive.
    """
    trimmed = haystack.rstrip()
    words = [w for w in words if w]
    if not words or not trimmed:
        return trimmed
    folded, index_map = _fold_with_index_map(trimmed)
    pattern = _word_pattern(*(_fold_for_match(w) for w in words)) + r"$"
    match = re.search(pattern, folded)
    if not match:
        return trimmed
    return trimmed[: index_map[match.start()]].rstrip()


def split_before_any(haystack: str, words) -> str:
    """
    Retorna o que vem ANTES da PRIMEIRA ocorrência de QUALQUER uma das
    `words` (cada uma casada como palavra/frase inteira, sem acento,
    sem diferenciar maiúscula/minúscula) em `haystack`. Se nenhuma das
    `words` aparecer, retorna `haystack` inteiro (só com as bordas
    aparadas).

    Ao contrário de split_after_word(), preserva CAPITALIZAÇÃO,
    ACENTO e PONTUAÇÃO ORIGINAIS de `haystack` — o resultado pode
    virar conteúdo real de ditado colado no chat (ver dictation.py),
    não é só comparado contra outro gatilho depois. Só apara
    ESPAÇO nas bordas (não pontuação — "?"/"!"/"." no fim de uma
    frase real dita pela pessoa tem que sobreviver; quem quer
    aparar pontuação porque o resultado NUNCA é mostrado pra ninguém
    é split_after_word(), não esta função). A posição do gatilho é
    traduzida do texto dobrado pro original por _fold_with_index_map()
    — dobrar NÃO preserva o comprimento em todos os casos (ver o
    porquê, com exemplos, na docstring de lá).

    Existe pra resgatar conteúdo dito no MESMO trecho transcrito que
    um gatilho de fechamento apareceu — sem isso, DictationSession
    descartava a frase inteira quando a wake word ou um dos
    CLOSE_TRIGGERS vinha colado no fim do que a pessoa disse (comum:
    terminar a frase e já emendar "over"/"câmbio" no mesmo trecho de
    ~4s do Whisper, sem pausa pro meio).
    """
    words = [w for w in words if w]
    if not words:
        return haystack.strip()

    haystack_folded, index_map = _fold_with_index_map(haystack)
    pattern = _word_pattern(*(_fold_for_match(w) for w in words))
    match = re.search(pattern, haystack_folded)
    if not match:
        return haystack.strip()
    # index_map: ver comentário equivalente em text_after_word().
    return haystack[:index_map[match.start()]].strip()

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
import string
import unicodedata

# Whitespace + pontuação — usado pra aparar sobra de pontuação nas
# bordas de um trecho já isolado (ex.: o que vem depois da wake word).
# Existe porque o Whisper adiciona pontuação de frase com frequência
# mesmo em falas curtas (ex.: transcreve só a wake word como
# "vIsper." com ponto final) — sem aparar isso, um resto que deveria
# contar como "nada depois da wake word" sobra como "." (não-vazio) e
# o comando inteiro falha silenciosamente. Ver split_after_word().
_EDGE_CHARS = string.whitespace + string.punctuation


def fold_accents(text: str) -> str:
    """Remove acentos (á→a, ç→c, ã→a...) pra comparação tolerante a
    erro de transcrição do Whisper com/sem acento — "câmbio" e
    "cambio" precisam contar como a mesma palavra."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def contains_word(haystack: str, word: str) -> bool:
    """
    True se `word` aparece em `haystack` como palavra (ou frase)
    inteira — não como substring dentro de outra palavra maior.
    Ignora maiúscula/minúscula e acento dos dois lados. `word` pode
    ter espaço dentro (frases tipo "claude code" funcionam igual).
    """
    if not word:
        return False
    haystack_folded = fold_accents(haystack.lower())
    word_folded = fold_accents(word.lower())
    pattern = r"\b" + re.escape(word_folded) + r"\b"
    return re.search(pattern, haystack_folded) is not None


def split_after_word(haystack: str, word: str) -> str:
    """
    Retorna o que vem depois da PRIMEIRA ocorrência de `word` como
    palavra inteira em `haystack`, ou string vazia se não achar (ou se
    só sobrar pontuação — ver _EDGE_CHARS).

    O retorno já vem sem acento e em minúsculas (mesmo tratamento do
    `haystack`) — funciona bem porque quem usa isso só compara contra
    outros gatilhos depois, nunca mostra esse texto pro usuário.
    """
    haystack_folded = fold_accents(haystack.lower())
    word_folded = fold_accents(word.lower())
    match = re.search(r"\b" + re.escape(word_folded) + r"\b", haystack_folded)
    if not match:
        return ""
    return haystack_folded[match.end():].strip(_EDGE_CHARS)


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
    haystack_folded = fold_accents(haystack.lower())
    word_folded = fold_accents(word.lower())
    match = re.search(r"\b" + re.escape(word_folded) + r"\b", haystack_folded)
    if not match:
        return ""
    return haystack[match.end():].lstrip(_EDGE_CHARS).rstrip()


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
    é split_after_word(), não esta função). Isso é seguro porque
    fold_accents()+lower() preservam o comprimento da string caractere
    a caractere pra acentuação comum em PT/EN (á,ã,â,à,ç,é,ê,í,ó,ô,õ,ú
    etc.) — a posição do match no texto "dobrado" bate com a mesma
    posição no texto original.

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

    haystack_folded = fold_accents(haystack.lower())
    alternatives = "|".join(re.escape(fold_accents(w.lower())) for w in words)
    match = re.search(r"\b(?:" + alternatives + r")\b", haystack_folded)
    if not match:
        return haystack.strip()
    return haystack[:match.start()].strip()

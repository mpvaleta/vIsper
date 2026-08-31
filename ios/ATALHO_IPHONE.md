# vIsper no iPhone — sem Xcode, sem conta paga

## Por que NÃO existe um "DMG do iPhone"

`.dmg` é formato de macOS. iOS não instala app de arquivo: ou vem da
App Store, ou é compilado no Xcode e assinado. Com conta grátis de
desenvolvedor o app **expira em 7 dias** e precisa ser reinstalado
pelo cabo; sem expirar são US$99/ano. Nenhuma das duas combina com o
princípio de custo zero deste projeto (ver CLAUDE.md).

O caminho abaixo usa o app **Atalhos**, que já vem instalado no seu
iPhone. Faz exatamente o que o rascunho Swift (`SendToVisperIntent.swift`)
faria — publicar o comando no tópico ntfy que o Mac escuta — só que
sem compilar nada, sem expirar, e funcionando também no Apple Watch.

**Pré-requisito:** o `NTFY_TOPIC` já configurado no `config.py` do Mac
e o vIsper rodando lá. Sem isso não há quem escute.

---

## Montando o Atalho (uma vez, ~3 minutos)

1. Abra **Atalhos** → **+** (canto superior direito).

2. **Adicionar ação** → busque **"Ditar texto"**. Toque no idioma
   dentro da ação e escolha **Português (Brasil)** (ou Inglês, o que
   for falar).

3. **Adicionar ação** → busque **"Texto"**. No campo, escreva:

   ```
   vIsper Ditar texto over
   ```

   Só que "Ditar texto" no meio precisa ser a **variável**, não a
   palavra digitada: apague essas duas palavras e, com o cursor ali,
   toque na sugestão **Texto Ditado** que aparece logo acima do
   teclado. Deve ficar `vIsper` + variável azul + `over`.

   *O que isso faz:* monta a frase completa que o Mac espera, então
   você só dita o conteúdo. Falando "claude qual é a previsão do
   tempo" o Mac recebe `vIsper claude qual é a previsão do tempo over`
   — abre o Claude, cola a pergunta e aperta Enter, tudo num disparo
   só.

   **Importante — sempre comece ditando o nome de uma IA**
   ("claude", "chatgpt", "perplexity" ou "gemini"), igual ao exemplo
   acima. O Mac só abre alguma coisa se um desses nomes vier logo
   depois de "vIsper" — sem um deles, a mensagem chega e não abre
   NADA, sem erro nenhum dos dois lados (o "over" que este Atalho
   sempre gruda no fim impede o comportamento padrão de "só a wake
   word abre a IA de sempre" de valer aqui). Ex.: dite "claude qual é
   a previsão do tempo", nunca só "qual é a previsão do tempo".

4. **Adicionar ação** → busque **"Obter conteúdo do URL"**.
   - No campo URL: `https://ntfy.sh/SEU_TOPICO`
     (troque `SEU_TOPICO` pelo tópico de verdade — **não** o
     `NTFY_TOPIC` que aparece em `config.py`: esse arquivo é
     versionado e público, então `NTFY_TOPIC` nele é sempre `""`. O
     valor de verdade está no link que `python3 setup_visper.py`
     imprimiu/copiou, ou em
     `~/Library/Application Support/vIsper/settings.json` no Mac —
     tem que ser idêntico, sem `https://` duplicado)
   - Toque em **Mostrar mais**
   - **Método**: mude de GET pra **POST**
   - **Corpo da solicitação**: mude pra **Arquivo**
   - No campo que aparece, escolha a variável **Texto** (o resultado do
     passo 3)

5. Toque no nome do atalho lá em cima → renomeie pra **vIsper**.
   O nome vira o comando da Siri, então escolha algo fácil de falar.

Pronto. Toque no atalho pra testar: ele deve pedir o microfone,
escutar, e o Mac reagir na hora.

---

## Disparando sem tocar na tela

Com o atalho salvo, todos estes caminhos já funcionam de graça:

- **Siri** — "Ei Siri, vIsper"
- **Botão de Ação** (iPhone 15 Pro ou mais novo) — Ajustes → Botão de
  Ação → deslize até **Atalho** → escolha vIsper
- **Tela de Bloqueio / Tela de Início** — segure o atalho na lista →
  Compartilhar → Adicionar à Tela de Início, ou use o widget de
  Atalhos
- **Apple Watch** — o atalho aparece sozinho no app Atalhos do relógio
  (é o caso de uso do treino que motivou o relay; nada a mais pra
  configurar)

---

## Se não funcionar

| Sintoma | Provável causa |
|---|---|
| Atalho roda, Mac não reage | Tópico diferente entre iPhone e o vIsper (ver passo 4 — não é o `NTFY_TOPIC` de `config.py`), ou o vIsper não está rodando no Mac |
| Erro de rede no atalho | URL malformada — confira se é `https://ntfy.sh/topico`, sem barra no fim |
| Mac reage mas não cola nada | Permissão de Acessibilidade faltando no Mac (ver README) |
| Abre a IA mas fica esperando | O `over` do passo 3 não entrou na frase — confira que ele está DEPOIS da variável |
| Nada acontece, nenhum erro em lugar nenhum | Você não começou ditando o nome de uma IA (ver aviso no passo 3) — "qual é a previsão" sozinho não abre nada; tem que ser "claude qual é a previsão" |

Teste o lado do Mac isolado antes de culpar o iPhone — pelo Terminal
do próprio Mac:

```bash
curl -d "vIsper claude teste over" https://ntfy.sh/SEU_TOPICO
```

Se isso não funcionar, o problema é no Mac e o iPhone não tem chance.

---

## E o `SendToVisperIntent.swift`?

Continua no repositório como caminho avançado, pra caso um dia você
queira um app de verdade na tela de início (ícone próprio, sem passar
pelo app Atalhos). Ele exige Xcode, um Mac pra compilar, e conta de
desenvolvedor pra não expirar em 7 dias — e **nunca foi compilado nem
testado**. Enquanto o Atalho acima resolver, ele não é necessário.

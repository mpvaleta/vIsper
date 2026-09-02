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

**Pré-requisito:** o vIsper rodando no Mac e já com um tópico do ntfy
configurado. Sem isso não há quem escute.

O tópico **não** fica no `config.py` — esse arquivo é público, e o
tópico é, na prática, a senha que impede qualquer pessoa do mundo de
disparar automação no seu Mac. Ele mora fora do repositório. Pra
descobrir o seu, escolha o caminho que combina com como você instalou:

| Como você instalou | Onde está o tópico |
|---|---|
| Pelo `.dmg` | No próprio app: menu do vIsper → **iPhone connection…**. Ele mostra o tópico atual; se ainda não houver nenhum, digite `new` ali e o vIsper sorteia um, mostra na tela e copia pro clipboard |
| Pelo repositório | O link que `python3 setup_visper.py` imprime e copia, ou `~/Library/Application Support/vIsper/settings.json` |

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

   **Dizer o nome da IA é opcional.** Se você começar ditando
   "claude", "chatgpt", "perplexity" ou "gemini", abre aquela; se não
   disser nenhum, abre a sua IA padrão (`DEFAULT_AI`, que vem como
   Claude). Ou seja, "qual é a previsão do tempo" sozinho funciona.

   *(Isso mudou: até pouco tempo atrás, uma mensagem sem nome de IA
   chegava no Mac e não abria NADA, sem erro nenhum dos dois lados —
   porque o "over" que este Atalho sempre gruda no fim impedia o
   comportamento de "só a wake word abre a IA de sempre" de valer
   aqui. Se o seu Mac ainda estiver numa versão antiga do vIsper e
   nada acontecer, é isso: ou atualize o app, ou volte a começar
   dizendo o nome da IA.)*

   **A wake word do passo 3 tem que ser a MESMA do Mac.** O padrão é
   "vIsper" nos dois lados. Se você trocou no Mac (menu → **Wake
   word…**), troque aqui também — senão a mensagem chega e não bate
   com nada. Pra conferir o que o Mac está recebendo de verdade, veja
   **Recent activity…** no menu dele: toda mensagem vinda do telefone
   aparece ali marcada como `phone`, mesmo quando não casa com nada.

4. **Adicionar ação** → busque **"Obter conteúdo do URL"**.
   - No campo URL: `https://ntfy.sh/SEU_TOPICO`
     (troque `SEU_TOPICO` pelo tópico de verdade — o mesmo do
     pré-requisito lá em cima. Tem que ser idêntico ao do Mac, sem
     `https://` duplicado)
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

**Antes de qualquer coisa: abra o menu do vIsper no Mac → Recent
activity…** Toda mensagem que chega do telefone aparece ali marcada
como `phone`, com o texto exato que o Mac recebeu, mesmo quando ela
não casa com nada. Isso separa em um olhar "não chegou" de "chegou e
não bateu com nada" — que é a dúvida que costuma custar meia hora.

| Sintoma | Provável causa |
|---|---|
| Nada em "Recent activity" | O Mac não recebeu: tópico diferente entre iPhone e vIsper (ver o pré-requisito lá em cima — não é o `NTFY_TOPIC` de `config.py`), ou o vIsper não está rodando |
| Aparece em "Recent activity" mas não abre nada | A wake word do Atalho não bate com a do Mac (passo 3), ou está escrita diferente do que o Mac espera |
| Erro de rede no atalho | URL malformada — confira se é `https://ntfy.sh/topico`, sem barra no fim |
| Mac reage mas não cola nada | Permissão de Acessibilidade faltando no Mac (ver README) |
| Abre a IA mas fica esperando | O `over` do passo 3 não entrou na frase — confira que ele está DEPOIS da variável |
| Abre o Claude Code em vez do Claude, ou some sem explicação | Você ditou algo começando com "code"/"código" logo depois de "claude". Pelo Atalho o texto é livre, então isso ainda pode acontecer — dite "claude, revisa este código" em vez de "claude código revisa". (No app de iPhone via navegador isso já não acontece mais: lá o chip manda a IA escolhida separada do texto.) |

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

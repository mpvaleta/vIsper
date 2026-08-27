# vIsper

Fala a palavra de ativação + o nome de uma IA, e ele abre o chat certo
(Claude, Claude Code, Perplexity, ChatGPT, Gemini). Depois disso, tudo
que você falar vira sua mensagem — quando terminar, fale "câmbio" (ou
"over", ou a palavra de ativação de novo) que ele cola tudo no chat e
aperta Enter. Nenhum outro app de ditado é necessário.

Tudo numa respiração só também funciona, e é o jeito mais natural de
usar:

> "vIsper claude qual é a previsão do tempo **over**"

## O caminho curto (se você só quer usar)

1. **Mac:** baixe o DMG (aba Actions → última execução ✅ → Artifacts),
   arraste pra Applications, **botão direito → Abrir** na primeira vez.
2. Espere o ícone **âmbar** da barra de menu virar **cinza** (primeira
   vez baixa o modelo, ~150 MB), clique → **Start listening**, e
   autorize Microfone e Acessibilidade quando o macOS pedir.
3. Fale: **"vIsper claude oi over"**. Pronto — o resto deste README é
   detalhe.

E ele tolera erro de pronúncia/transcrição: "whisper claude",
"vIsper cloud" e parecidos funcionam igual (ver "Se ele não te
reconhece", abaixo).

---

## Instalar no Mac

### O jeito fácil — baixar o app pronto

O `.dmg` é compilado num Mac de verdade pelo GitHub a cada mudança no
código. Pra baixar:

1. Vá na aba **[Actions](https://github.com/mpvaleta/vIsper/actions/workflows/build-macos.yml)**
   → clique na execução mais recente com ✅ → role até **Artifacts** no
   fim da página, e baixe **`vIsper-AppleSilicon`** (Macs com chip M1,
   M2, M3 ou M4 — confira em menu  → **Sobre este Mac** se aparecer
   "Chip: Apple M...").

   Vem num `.zip` (o GitHub sempre compacta artefato); descompacte e o
   `.dmg` está lá dentro. Precisa estar logada no GitHub pra baixar.

   *Mac Intel (pré-2020)?* O GitHub aposentou os runners Intel, então
   não há DMG pronto pra essa arquitetura — use o caminho de
   desenvolvedor logo abaixo (funciona igual), ou rode
   `./build_mac_app.sh` na própria máquina pra gerar o seu.

   > Quer a página de **Releases**, com link direto e sem login? É um
   > comando, na pasta do vIsper:
   > ```bash
   > git tag v0.1.0 && git push origin v0.1.0
   > ```
   > Isso dispara o mesmo build e anexa os dois DMGs numa Release de
   > verdade. (Eu não consigo fazer isso daqui — o ambiente onde este
   > código foi escrito só tem permissão de push pro branch, não pra
   > tags: `403` ao tentar.)

2. Abra o `.dmg` e arraste o vIsper pra pasta Applications.

3. **Na primeira vez, abra com botão direito → Abrir.** O duplo clique
   normal é bloqueado porque o app não é assinado por uma conta paga da
   Apple (US$ 99/ano, contra o custo zero deste projeto). Só na
   primeira vez; depois o duplo clique funciona.

4. Aparece o mascote em **âmbar** na barra de menu. Na primeiríssima
   execução ele baixa o modelo de transcrição (~150 MB), então precisa
   de internet e pode demorar alguns minutos. Quando virar **cinza**,
   está pronto.

5. Clique no ícone → **Start listening**. O macOS vai pedir permissão
   de **Microfone**; autorize.

6. Fale um comando. Na primeira vez que ele tentar colar, o macOS pede
   permissão de **Acessibilidade** — o próprio app te manda pro lugar
   certo (Ajustes do Sistema → Privacidade e Segurança →
   Acessibilidade). Ligue o vIsper lá e clique em Start listening de
   novo.

Pronto.

### O que o ícone está te dizendo

O ícone da barra de menu é o mascote do vIsper, e **a cor dele É o
estado** — a forma nunca muda (é como você acha ele entre os outros
ícones da barra), só a cor:

| Cor | Quer dizer |
|---|---|
| Âmbar | Carregando o modelo de transcrição (só na primeira vez demora) |
| Cinza | Pronto, mas **não** está escutando — clique em Start listening |
| Verde | Escutando, esperando a palavra de ativação |
| Coral | Te ouviu, está acumulando o ditado |
| Azul | Acabou de colar e mandar (volta pro verde em ~2s) |
| Terracota | Algo falhou — abra o menu, a explicação está lá |

Dentro do menu tem também **Heard:** — a última coisa que ele entendeu,
com o **idioma que ele detectou** na frente (ex.: `[pt] oi tudo bem`).
Esse é o primeiro lugar pra olhar quando parecer que ele te ignorou:
quase sempre ele ouviu, só que transcreveu a palavra de ativação de
outro jeito, ou detectou o idioma errado (ver "Se ele não te
reconhece", abaixo).

### O jeito de desenvolvedor — rodar do código

Precisa de **Python 3.10, 3.11 ou 3.12** (o 3.13 ainda não tem as
bibliotecas de que isso depende; o 3.9 que já vem no macOS roda o app
mas não empacota o `.app`).

```bash
brew install portaudio python@3.11

cd vIsper
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python3 setup_visper.py   # configura (opcional, mas recomendado)
python3 doctor.py         # confere se está tudo certo
python3 main.py           # abre o ícone na barra de menu
```

Pra gerar o `.app`/`.dmg` você mesmo: `./build_mac_app.sh`
(ou `./build_mac_app.sh --dev` pra um build de segundos, que só
funciona enquanto a pasta não sair do lugar).

---

## Instalar no iPhone

**Não existe DMG de iPhone** — iOS só instala app pela App Store ou
compilado no Xcode, e com conta grátis o app expira em 7 dias. O
caminho abaixo não custa nada, não expira, e leva 1 minuto.

1. No **Mac**, rode `python3 setup_visper.py`. Ele imprime (e copia) um
   link.
2. Mande esse link pro iPhone — AirDrop, Notas, ou uma mensagem pra
   você mesma.
3. Abra o link **no Safari do iPhone**.
4. Toque em **Compartilhar** → **Adicionar à Tela de Início**.

Vira um ícone que abre como app. Fale e ele manda pro Mac sozinho —
de qualquer lugar com internet, não só na Wi-Fi de casa.

**Você não precisa apertar "Send to Mac".** Assim que você para de
falar (ou de digitar), ele espera ~2,5 segundos e começa uma contagem
de 3 segundos — o botão vira **Tap to cancel** e um anel se fecha em
volta dele. Não tocou em nada, foi. Isso vale pelos dois caminhos: o
botão de microfone do app **e** a tecla de microfone do teclado do
próprio iPhone (que é a que sempre funciona, mesmo quando o iOS não
dá o reconhecimento de voz pro app). Continuar escrevendo cancela a
contagem e recomeça a espera, então corrigir uma palavra não te
obriga a apertar nada. Dá pra desligar tudo isso em **Settings** →
*Auto-send when you stop*.

> **Faça o passo 4 antes de fechar o Safari.** No iOS, o app da tela de
> início tem armazenamento separado do Safari; o que leva sua conexão
> pra lá é o link. Se fechar antes, é só abrir o link de novo.

Instalado pelo `.dmg` e sem Terminal à mão? Dá pra configurar o mesmo
tópico pelo menu do app: **Settings…**

Prefere a Siri e o Apple Watch em vez de um ícone? Tem uma receita pro
app Atalhos em [`ios/ATALHO_IPHONE.md`](ios/ATALHO_IPHONE.md) — funciona
junto, os dois usam o mesmo tópico.

### Segurança — leia esta parte

O iPhone fala com o Mac por um tópico do
[ntfy](https://ntfy.sh), que é gratuito e não pede senha. Isso quer
dizer que **o nome do tópico É a senha**: quem souber ele consegue
disparar automação de verdade no seu Mac.

Por isso:

- O `setup_visper.py` sorteia um nome longo e aleatório. Não troque por
  algo "fácil de lembrar".
- Ele fica em `~/Library/Application Support/vIsper/settings.json`,
  **fora do repositório** — este repositório é público, e um `git push`
  distraído publicaria a chave da sua casa.
- Desconfiou que vazou? Rode o `setup_visper.py` de novo: sorteia
  outro, e o antigo deixa de valer na hora.
- Por padrão o iPhone **não** pode abrir o Claude Code, porque isso
  abriria o Terminal e digitaria dentro dele — vazar o tópico deixaria
  de ser "digitar num chat" e viraria execução de comando. Pelo
  microfone local continua funcionando normalmente. Pra mudar, ver
  `RELAY_BLOCKED_AIS` em `config.py`.
- O texto passa em claro pelo servidor público do ntfy.sh. Não mande
  senha, dado bancário nem nada sigiloso por ali.

---

## Se ele não te reconhece

Isso agora tem **duas camadas de defesa automáticas**, porque a palavra
"vIsper" é inventada e o transcritor erra a grafia dela com frequência:

1. **O transcritor é avisado do vocabulário.** A wake word, os nomes
   das IAs e "câmbio"/"over" entram como prioridade na transcrição
   (parâmetro `hotwords` do faster-whisper) — o erro acontece menos.
2. **Quando ainda erra, o casamento tolera.** "whisper", "vesper",
   "vísper" contam como "vIsper"; "cloud" e "clode" contam como
   "claude". Os limiares foram medidos contra transcrições reais — e
   contra as palavras de ditado mais parecidas, pra não colar em coisa
   errada ("dispersar" não dispara nada).

A tolerância vale **só pra abrir**. Pra fechar/mandar ("câmbio",
"over", ou a wake word de novo) o casamento é exato de propósito:
mandar a mensagem pela metade por um falso positivo é bem pior do que
abrir uma aba à toa. Ajuste fino em `FUZZY_MATCH_THRESHOLD`
(`config.py`) — 1.0 desliga a tolerância.

Se mesmo assim parecer surdo: abra o menu e veja o **Heard:**, que
mostra o que ele realmente entendeu — é a diferença entre "não me
ouviu" e "ouviu mas escreveu diferente". Trocar a palavra de ativação
por uma REAL ("Vésper", "Íris") ajuda mais ainda:

```bash
python3 setup_visper.py    # ele pergunta a palavra de ativação
```

A solução definitiva continua sendo o Porcupine (mais abaixo), que
reconhece o SOM da palavra em vez de tentar escrever ela.

### "Só funciona em inglês" (ou só em português)

Sintoma comum: você fala português e o **Heard:** mostra `[en]` na
frente — o Whisper detectou o idioma ERRADO, não é que ele não
entenda português. Detecção automática é pouco confiável em trechos
CURTOS de fala (limitação conhecida do modelo, não bug daqui) — e o
vIsper escuta em blocos de ~4 segundos. O problema não para no
rótulo: o Whisper **transcreve no idioma que ele achou**, então
detecção errada vira texto errado.

Por isso o vIsper não deixa mais ele adivinhar à vontade: você diz
quais idiomas VOCÊ fala, e ele nunca transcreve em nada fora dessa
lista. O padrão já vem `pt, en`.

```bash
python3 setup_visper.py    # pergunta "que idioma(s) você fala"
```

- `pt` (um só) — pula a detecção por completo. **É o mais
  confiável**, escolha esse se você dita sempre no mesmo idioma.
- `pt, en` (o padrão) — alterna entre os dois com segurança: se o
  palpite não estiver na sua lista, ou vier sem confiança, ele
  **transcreve de novo** forçando o idioma que estava dando certo.
- `auto` — sem restrição nenhuma (aceita o erro de detecção junto).

Quando ele corrige um palpite, o **Heard:** mostra as duas pontas
(`[en→pt] bom dia`) — assim dá pra ver que a correção funcionou em
vez de ficar no escuro.

---

## Microfone

O vIsper reconhece automaticamente, nesta ordem: **DJI Mic** (é só
plugar o receiver por USB-C — não precisa do app da DJI), depois **fone
Bluetooth** (Sony WH-1000XM5/WF-1000XM5). Se nenhum dos dois estiver
por perto, usa o **microfone padrão do Mac**, então ele funciona de
cara mesmo sem equipamento nenhum.

Pra forçar um específico: menu → **Microphone**. A escolha fica salva e
volta sozinha da próxima vez.

### Aviso sobre fone Bluetooth

Usar o microfone de um fone Bluetooth clássico (AirPods, Sony XM5,
qualquer um) força o Mac a trocar o perfil dele de A2DP pra HFP/HSP — o
mesmo de ligação telefônica. Isso derruba a qualidade do **áudio do
sistema inteiro** pra mono enquanto a escuta estiver ativa. Se você
estiver ouvindo música e clicar em Start listening, o som vai piorar
até você clicar em Stop listening.

**Isso é do protocolo Bluetooth, não um bug do vIsper** — nenhum app
consegue evitar. O vIsper avisa por notificação quando detecta um fone.

Outro fone que não é reconhecido sozinho? Escolha no menu, ou
acrescente as palavras-chave do nome dele em `PREFERRED_INPUT_DEVICES`
(`config.py`). Rode `python3 doctor.py` pra ver o nome exato que o seu
macOS usa.

---

## Ajustar o comportamento

O que muda o dia a dia se configura pelo `python3 setup_visper.py` ou
pelo menu **Settings…** do app. Os padrões (e as opções mais raras)
estão no `config.py`:

- `WAKE_WORD` — a palavra de ativação
- `DEFAULT_AI` — qual IA abre se você falar só a palavra de ativação
- `AI_TRIGGERS` — apelidos de cada IA, em quantos idiomas quiser
- `CLOSE_TRIGGERS` — o que manda ver sem repetir a palavra de ativação.
  Padrão: `"câmbio"` e `"over"`, emprestados do vocabulário de rádio
  ("terminei de falar, sua vez"). Escolhidos por serem raros o
  bastante em fala natural pra não disparar sem querer no meio do seu
  ditado — ao contrário de "manda"/"pronto"/"send", que são comuns
  demais. Casam como palavra inteira, então "over" não confunde com
  "however" nem "discover".
- `PREFERRED_INPUT_DEVICES` — quais microfones são reconhecidos
  sozinhos, em ordem de prioridade
- `FUZZY_MATCH_THRESHOLD` — quão tolerante a abertura é com erro de
  transcrição (0.72 padrão, medido; 1.0 = só casamento exato)
- `TRANSCRIPTION_LANGUAGES` — a lista de idiomas que você fala
  (`["pt", "en"]` por padrão). O vIsper nunca transcreve em nada fora
  dela; lista vazia = sem restrição. Ver "Só funciona em inglês",
  acima.
- `LANGUAGE_CONFIDENCE_THRESHOLD` — abaixo disso o palpite de idioma
  é descartado e o trecho é transcrito de novo (0.5 padrão)
- `CANCEL_TRIGGERS` — as palavras que descartam o ditado quando vêm
  logo depois da palavra de ativação (`"cancela"`, `"esquece"`…)
- `RELAY_BLOCKED_AIS` — o que o iPhone não pode abrir (ver Segurança)
- `DICTATION_OPEN_SOUND` / `DICTATION_SEND_SOUND` /
  `DICTATION_CANCEL_SOUND` — o som curto de abrir/mandar/cancelar.
  Usa sons que já vêm no macOS (Pop, Glass, Funk, Tink, Ping…).
  Útil de fone: dá pra saber que abriu/mandou sem olhar pra tela.
  `DICTATION_SOUNDS_ENABLED = False` desliga.

**Não coloque nada pessoal no `config.py`** — ele é versionado num
repositório público. Tópico do ntfy e chave do Porcupine se configuram
pelo `setup_visper.py`, que guarda tudo fora do repositório.

### Uma sessão completa

| Você fala | O que acontece |
|---|---|
| "vIsper, abre o ChatGPT" | Abre o ChatGPT, entra em modo ditado (ícone vira coral) |
| "preciso de um resumo do relatório de vendas" | Vira parte da sua mensagem |
| "do segundo trimestre, por favor" | Continua acumulando |
| "câmbio" | Cola tudo no chat e aperta Enter (ícone vira azul) |

### Desistir sem mandar

Se a transcrição saiu errada, ou você mudou de ideia no meio:

> "**vIsper, cancela**"

O ditado inteiro é jogado fora — nada é colado, nada é enviado — e o
vIsper volta a esperar um comando novo. O som é **diferente** do som de
enviar, de propósito: você precisa conseguir saber, sem olhar, se o
texto foi embora ou foi descartado.

Serve também `cancelar`, `cancel`, `esquece` e `forget it`. A palavra
precisa vir **logo depois** da palavra de ativação — é o que permite
ditar uma mensagem que fala em cancelar ("preciso cancelar a reserva")
sem que ela se apague sozinha.

Dois avisos que importam:

1. Só é reconhecido o que vier **depois** da palavra de ativação, pra
   evitar disparo à toa.
2. Durante o ditado, se a palavra de ativação ou um `CLOSE_TRIGGERS`
   aparecer sem querer no meio do que você está falando, a sessão corta
   ali e manda cedo demais. Palavras raras reduzem muito isso, mas não
   zeram — o Porcupine resolve melhor. (Aconteceu? "vIsper, cancela"
   antes de repetir.)

---

## Deixar rodando sozinho no login

Instalado pelo `.dmg`, é só: **Ajustes do Sistema → Geral → Itens de
Início → +** e escolher o vIsper. É o jeito mais simples e não precisa
de mais nada.

Rodando pelo código (`python3 main.py`), tem um LaunchAgent em
`launchd/com.valeta.visper.plist`:

1. Confirme que existe um `venv/` na pasta do vIsper com tudo
   instalado — o LaunchAgent aponta pra esse interpretador específico.
2. `cp launchd/com.valeta.visper.plist ~/Library/LaunchAgents/` e troque
   as 4 ocorrências de `TROQUE_AQUI_CAMINHO_ABSOLUTO_DO_VISPER` pelo
   caminho real (descubra com `pwd`).
3. `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.valeta.visper.plist`
4. Conferir: `launchctl list | grep com.valeta.visper`. Se o ícone não
   aparecer, os logs estão em `visper.out.log` / `visper.err.log`, na
   pasta do vIsper.

Pra desligar:
```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.valeta.visper.plist
rm ~/Library/LaunchAgents/com.valeta.visper.plist
```

**Escolha um dos dois, não os dois.** Itens de Início com o `.app` E o
LaunchAgent ao mesmo tempo abre duas cópias do vIsper, que vão brigar
pelo microfone.

O LaunchAgent reinicia o app se ele **crashar**, mas não reabre depois
de você clicar em Quit — a distinção é proposital.

---

## Porcupine — wake word de verdade (opcional)

Hoje o vIsper "ouve" a palavra de ativação transcrevendo tudo e
procurando ela no texto. O Porcupine reconhece o **som** da palavra, o
que resolve tanto a falha em reconhecer quanto o corte precoce por
falso positivo. É grátis pra uso pessoal.

1. Conta grátis em `console.picovoice.ai`
2. Copie o **AccessKey** do painel
3. Na seção Porcupine, digite sua palavra e treine (não precisa gravar
   áudio nem saber nada de ML)
4. Baixe o arquivo `.ppn` pra macOS
5. `python3 setup_visper.py` → responda "sim" na pergunta do Porcupine

O Porcupine reconhece só a palavra de ativação, não os
`CLOSE_TRIGGERS` — cada palavra precisa do próprio treino.

---

## Estado do projeto — o que é testado e o que não é

Honestidade sobre o que foi validado de verdade:

| Peça | Como foi validada |
|---|---|
| Lógica do núcleo (roteamento, ditado, texto, config, barra de menu) | 298 testes automatizados |
| App de iPhone (`docs/`) | 39 testes num navegador de verdade (Chromium), a cada push |
| `.app` / `.dmg` | Compilado num macOS de verdade a cada push, com teste de que o app abre e não morre |
| Segredos fora do repositório | Verificado no CI a cada push |
| Microfone, permissões do macOS, barra de menu | Já rodou num Mac de verdade (ícone, escuta, permissões, download do modelo). Falta uma sessão inteira de ponta a ponta sem travar |
| Relay do ntfy | **Nunca testado contra o ntfy.sh real** (o sandbox onde foi escrito bloqueia) |
| Porcupine com áudio real | **Nunca testado** |
| LaunchAgent | **Nunca carregado por um launchctl de verdade** |

O que está na metade de baixo depende de hardware e de um Mac de
verdade — é o que só o seu teste vai dizer.

---

## O que ainda falta

1. **Upload de áudio direto** (voice notes do WhatsApp etc.) — o código
   existe (`audio_file_input.py`, testado com transcritor simulado),
   mas ainda não está ligado no menu.
2. **Feedback visual mais rico** — hoje o estado é o ícone colorido; o
   mockup em `design/layouts_mockup.html` mostra um painel bem mais
   completo.
3. **Windows/Linux** — a v1 é só Mac. `audio_input.py`,
   `command_router.py`, `dictation.py`, `text_utils.py` e `config.py`
   já são portáveis; `actions.py` e `main.py` precisariam de uma versão
   por sistema.

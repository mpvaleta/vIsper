# vIsper

Interface completa ativada por voz: fala a wake word + o nome de uma
IA, ele abre o chat certo (Claude, Claude Code, Perplexity, ChatGPT,
Gemini). Se falar só a wake word, abre a IA padrão. Depois disso, tudo
que você falar é acumulado como sua mensagem — quando terminar, fale
a wake word de novo (com qualquer palavra junto) que ele cola tudo no
chat e aperta Enter. Nenhum outro app de ditado é necessário. Dois
tipos de entrada são reconhecidos automaticamente — o receiver do DJI
Mic, ou um fone Bluetooth tipo o Sony WH-1000XM5/WF-1000XM5 — mas
funciona com qualquer microfone que o Mac reconheça, escolhido
manualmente no menu se preferir.

## Sobre o DJI Mic

Não precisa abrir o app da DJI pra isso funcionar. Basta plugar o
receiver via USB-C (ou pelo adaptador) no Mac — o macOS já detecta
ele automaticamente como dispositivo de entrada, normalmente com um
nome contendo "DJI" ou "Wireless Microphone RX". O app da DJI
(Mimo / DJI Mic) só entra em cena se você quiser ajustar o ganho do
mic ou monitorar o áudio na hora — não é necessário pra esse programa
capturar o som.

## Sobre usar fone de ouvido (Bluetooth)

Fones pareados por Bluetooth — testado pensando no Sony WH-1000XM5 e
WF-1000XM5 — também são reconhecidos automaticamente, do mesmo jeito
que o DJI Mic: o macOS já lista o fone conectado como dispositivo de
entrada normal, sem instalar nada. Se os dois estiverem disponíveis
ao mesmo tempo, o DJI Mic ganha por padrão (ver `PREFERRED_INPUT_DEVICES`
em `config.py`) — é um mic dedicado, sem o efeito colateral abaixo.

**Aviso importante de qualidade — isso é do protocolo Bluetooth, não
um bug do vIsper:** usar o microfone de um fone Bluetooth clássico
(AirPods, Sony XM5, qualquer um) força o Mac a trocar o perfil dele
de A2DP (estéreo, alta qualidade, só toca áudio) pra HFP/HSP — o
mesmo perfil usado em ligação telefônica. Isso derruba a qualidade do
**áudio do sistema inteiro** (não só da gravação) pra mono, enquanto
o stream de entrada estiver aberto — ou seja, se você estiver ouvindo
música ou podcast no fone e clicar em "Iniciar escuta", o som vai
piorar perceptivelmente até você clicar em "Parar escuta" (ou fechar
o app). O vIsper mostra uma notificação avisando isso na primeira vez
que detecta um fone Bluetooth em cada sessão de escuta.

Se o seu modelo não for reconhecido automaticamente (nome diferente
do esperado, ou outro fone que não o Sony XM5), duas opções: escolha
manualmente no menu "Escolher microfone", ou adicione as palavras-chave
do nome dele em `PREFERRED_INPUT_DEVICES` (`config.py`) — rode
`python3 doctor.py` pra ver o nome exato que o seu macOS usa antes de
escrever o keyword.

## Instalação

```bash
# dependência do sistema pro sounddevice conseguir acessar áudio
brew install portaudio

# venv dedicado, dentro da própria pasta do vIsper — recomendado (não
# só "boa prática" genérica): se você for configurar o LaunchAgent
# depois (ver "Deixar rodando sozinho", abaixo), ele precisa de um
# caminho de interpreter Python FIXO e não deve depender de qual
# python3 o PATH do seu shell resolve num dado momento. Use o mesmo
# venv pra tudo (aqui embaixo E no LaunchAgent) — assim as permissões
# do macOS (mic/Automação/Acessibilidade), que são concedidas por
# BINÁRIO específico, só precisam ser concedidas uma vez.
python3 -m venv venv
source venv/bin/activate   # repita isso em cada Terminal novo antes de rodar algo daqui

# dependências Python
pip install -r requirements.txt
```

Na primeira execução, o macOS vai pedir permissão de microfone pro
Terminal (ou pro app, se você empacotar depois) — autorize em
Ajustes do Sistema → Privacidade e Segurança → Microfone.

Como o comando "abre Claude Code" usa AppleScript pra controlar o
Terminal, o macOS também vai pedir permissão de Automação na primeira
vez — autorize também.

## Rodando

Antes de rodar de verdade, vale conferir a config:

```bash
python3 doctor.py
```

Isso confere dependências instaladas, se algum microfone preferido
(DJI Mic ou fone Bluetooth) está detectável agora, se o tópico do
ntfy não é um valor óbvio/curto, se a config do Porcupine (se usada)
está completa, e se `DEFAULT_AI` bate com algo em `AI_TRIGGERS` — sem
precisar de permissão de mic nem de nada rodando pra isso (só
enumera os dispositivos, não abre stream).

```bash
python3 main.py
```

Um ícone aparece na barra de menu. Clique nele para:
- **Escolher microfone** — submenu com todo dispositivo de entrada
  disponível no momento; clique num nome pra usar ele manualmente, ou
  em "Detectar automaticamente" pra voltar a deixar o vIsper escolher
  sozinho (DJI Mic > fone Bluetooth, ver `PREFERRED_INPUT_DEVICES` em
  `config.py`). Útil se o dispositivo certo não for detectado
  sozinho, ou se você quiser forçar um em especial. A escolha manual
  fica salva (`~/Library/Application Support/vIsper/device.json`) e
  volta sozinha da próxima vez que você abrir o vIsper — clicar em
  "Detectar automaticamente" esquece essa escolha salva também.
- **Iniciar escuta** — começa a ouvir e reagir aos comandos. Se nada
  tiver sido escolhido manualmente, tenta detectar de novo nesse
  instante (então ligar o fone Bluetooth DEPOIS de abrir o vIsper
  ainda funciona, sem precisar reiniciar o app)
- **Parar escuta** — pausa

## Deixar rodando sozinho, sem precisar abrir Terminal (LaunchAgent)

Depois que `python3 main.py` estiver funcionando bem manualmente
(ver acima) por uns dias, dá pra deixar o macOS iniciar o vIsper
sozinho no login, em segundo plano, sem precisar abrir Terminal toda
vez. Use um **LaunchAgent** — o jeito padrão do macOS pra isso
(reinicia sozinho se crashar, não depende da UI de Login Items
mudando entre versões do macOS).

**NUNCA TESTADO NUM MAC DE VERDADE** — mesma honestidade do resto
deste projeto: escrito contra a documentação real do formato
`launchd.plist` (não de memória vaga), e o XML foi validado com
`plistlib` (parser estrito, garante que está bem formado), mas
nenhum `launchctl` de verdade rodou isso ainda.

1. Confirme que já tem um venv em `venv/` dentro da pasta do vIsper
   (ver "Instalação", acima) com tudo instalado — o LaunchAgent
   aponta pra esse interpreter específico, não pro `python3` do
   sistema.

2. Copie o template e troque as 4 ocorrências de
   `TROQUE_AQUI_CAMINHO_ABSOLUTO_DO_VISPER` pelo caminho absoluto de
   verdade da pasta (ex.: `/Users/valeta/vIsper` — descubra o seu
   com `pwd` dentro da pasta):
   ```bash
   cp launchd/com.valeta.visper.plist ~/Library/LaunchAgents/
   # depois edite ~/Library/LaunchAgents/com.valeta.visper.plist e troque o placeholder
   ```

3. Carregue o LaunchAgent:
   ```bash
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.valeta.visper.plist
   ```
   (Se o Mac estiver numa versão mais antiga do macOS e isso der erro,
   tente o comando clássico equivalente:
   `launchctl load ~/Library/LaunchAgents/com.valeta.visper.plist`.)

4. Confirme que carregou e que o ícone apareceu na barra de menu:
   ```bash
   launchctl list | grep com.valeta.visper
   ```
   Se o ícone não aparecer, olhe os logs (sem Terminal aberto, é pra
   onde print()/erro vão agora):
   ```bash
   cat ~/vIsper/visper.out.log   # troque pelo caminho real
   cat ~/vIsper/visper.err.log
   ```

5. Pra desligar o início automático (voltar a rodar só manualmente):
   ```bash
   launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.valeta.visper.plist
   rm ~/Library/LaunchAgents/com.valeta.visper.plist
   ```

Detalhe importante do comportamento: o LaunchAgent só reinicia o
vIsper sozinho se ele **crashar** (saída com erro) — clicar em "Sair"
no menu é uma saída deliberada seu e não reabre sozinho, de propósito
(`KeepAlive`/`SuccessfulExit` no plist).

## Como customizar (`config.py`)

Tudo que você provavelmente vai querer mexer está em `config.py`, não
espalhado pelo resto do código:

- `WAKE_WORD` — a palavra/frase de ativação. Troque à vontade.
- `DEFAULT_AI` — qual IA abre se você disser só a wake word.
- `AI_TRIGGERS` — apelidos de cada IA, em quantos idiomas quiser.
- `PREFERRED_INPUT_DEVICES` — quais microfones/fones são reconhecidos
  automaticamente, em ordem de prioridade (hoje: DJI Mic, depois Sony
  WH-1000XM5/WF-1000XM5). Cada grupo é `{"keywords": [...],
  "bluetooth": bool}` — adicione um grupo novo pra reconhecer outro
  fone/mic seu, ou reordene se quiser que outro dispositivo ganhe do
  DJI quando os dois estiverem disponíveis. A flag `"bluetooth"`
  controla só se o aviso de qualidade (ver "Sobre usar fone de
  ouvido", acima) aparece ou não.
- `DICTATION_SOUNDS_ENABLED` / `DICTATION_OPEN_SOUND` / `DICTATION_SEND_SOUND`
  — earcon (som curto) quando o ditado abre e quando manda ver. Usa
  sons já embutidos no macOS (`/System/Library/Sounds/*.aiff` — Pop,
  Glass, Tink, Ping, etc., troque o nome à vontade), sem precisar de
  nenhum arquivo extra. Especialmente útil usando fone de ouvido: dá
  pra saber que abriu/mandou sem olhar pra barra de menu — ex. durante
  o treino. `DICTATION_SOUNDS_ENABLED = False` desliga completamente.
- `CLOSE_TRIGGERS` — palavras que, durante o ditado, mandam ver sem
  precisar repetir a wake word. Padrão: `"câmbio"` (PT) e `"over"`
  (EN) — vocabulário emprestado de comunicação por rádio ("terminei
  de falar, sua vez"), escolhido de propósito por serem raros o
  bastante em fala natural pra não disparar sem querer no meio do que
  você está ditando (ao contrário de palavras comuns tipo
  "manda"/"send" ou "pronto"/"done"). Casam como palavra inteira
  (`text_utils.py`), então "over" não confunde com "however" nem
  "discover" no meio de uma frase em inglês.

Uma sessão completa com a wake word padrão ("vIsper"):

| Você fala | O que acontece |
|---|---|
| "vIsper, abre o ChatGPT" | Abre chat.openai.com, entra em modo ditado |
| "preciso de um resumo do relatório de vendas" | Vira parte da sua mensagem (não faz nada visível ainda) |
| "do segundo trimestre, por favor" | Continua acumulando |
| "câmbio" (ou "over", ou "vIsper" de novo) | Cola a mensagem inteira no chat e aperta Enter |

Se, em vez de um nome de IA, você disser só a wake word sozinha, abre
a IA definida em `DEFAULT_AI` e já entra em modo ditado do mesmo
jeito. "vIsper, abre Claude Code" continua abrindo o Terminal e
rodando `claude`, sem modo ditado (isso é específico do fluxo web).

**Importante — três avisos:**
1. Toda ação só é reconhecida se vier depois da wake word na mesma
   frase, pra evitar disparo à toa por palavra comum do dia a dia.
2. Durante o ditado, se a wake word OU um dos `CLOSE_TRIGGERS`
   aparecer sem querer no meio do que você está falando (por erro de
   transcrição ou ruído, ou porque a frase genuinamente continha
   aquela palavra), a sessão corta ali e manda cedo demais. Escolher
   palavras raras pro `CLOSE_TRIGGERS` reduz isso bastante, mas não
   zera — o motor de wake-word de verdade (Porcupine, abaixo) resolve
   melhor ainda, porque detecta o SOM da wake word, não texto
   transcrito. Isso hoje só vale pra wake word em si — os
   `CLOSE_TRIGGERS` novos ainda não têm detecção acústica própria
   (cada palavra que o Porcupine reconhece precisa do próprio treino
   em console.picovoice.ai).
3. Colar o texto e apertar Enter usa o **System Events**, que precisa
   de permissão de **Acessibilidade** (não só Automação) pro
   Terminal/Python, em Ajustes do Sistema → Privacidade e Segurança
   → Acessibilidade.

## Usar do iPhone, de qualquer lugar (`relay_listener.py` + ntfy)

Pra disparar comando do iPhone mesmo fora da Wi-Fi de casa (ex.:
durante o treino), o Mac escuta um tópico privado no
[ntfy](https://ntfy.sh) — um serviço gratuito e open-source de
pub/sub por HTTP — e o iPhone publica o comando nesse mesmo tópico
de onde estiver.

Configurar o lado do Mac:

1. Gerar um nome de tópico longo e aleatório (**nunca** um nome óbvio
   — tópicos do ntfy.sh são públicos por padrão, e isso aciona
   automação de verdade no seu Mac):
   ```bash
   python3 -c "import secrets; print('visper-' + secrets.token_urlsafe(24))"
   ```
2. Colar o resultado em `NTFY_TOPIC` no `config.py`.
3. Rodar `main.py` normalmente — se `NTFY_TOPIC` não estiver vazio,
   o relay liga sozinho numa thread separada, sem precisar de nada
   no menu.

Testar manualmente sem precisar do app de iPhone ainda (troque
`SEU_TOPICO` pelo valor real):
```bash
curl -d "vIsper claude confirma o teste" https://ntfy.sh/SEU_TOPICO
```
Isso deve abrir o Claude e colar o texto, exatamente como se tivesse
sido falado no mic local.

O lado do iPhone (`ios/SendToVisperIntent.swift`) é um **rascunho
ainda não compilado** — escrito sem acesso a Xcode. Precisa: criar um
projeto Xcode novo, colar o arquivo dentro, trocar o placeholder do
tópico pelo mesmo valor de `NTFY_TOPIC`, e testar de ponta a ponta.

## Limite atual do reconhecimento de wake word

Hoje o app usa Whisper (transcrição geral) pra "ouvir" a wake word —
ele tenta escrever a palavra que você disse. Se `WAKE_WORD` for uma
palavra inventada (tipo "vIsper" mesmo), o Whisper pode transcrever
errado e o comando falha silenciosamente. Funciona melhor com wake
words que sejam palavras reais e distintas.

## Próximo passo recomendado: Porcupine

Pra ter uma wake word de verdade — que reconhece o *som* da palavra
escolhida, não uma transcrição escrita — o caminho é o motor
**Porcupine** (Picovoice). Ele deixa treinar uma palavra 100%
personalizada, mesmo inventada, digitando ela num site (não precisa
gravar áudio nem saber ML), e evita tanto falha em reconhecer a wake
word quanto corte precoce do ditado por falso positivo.

O wrapper já existe (`wake_word_porcupine.py`, testado no que dá pra
testar sem os dados abaixo) — falta só a integração em `main.py`
(dois loops de áudio rodando junto, ver nota no topo do arquivo) e os
dois valores que só você consegue pegar:

1. Criar conta grátis em `console.picovoice.ai`
2. Copiar o **AccessKey** da conta (fica no painel principal, não
   precisa treinar nada pra conseguir esse valor)
3. Na seção Porcupine, digitar a wake word e treinar
4. Baixar o arquivo `.ppn` gerado pra macOS
5. Colar os dois em `config.py`: `PORCUPINE_ACCESS_KEY` (o do passo 2)
   e `PORCUPINE_KEYWORD_PATH` (caminho do `.ppn` do passo 4)

Vale checar o limite atual do plano grátis deles ao criar a conta —
os planos mudam com frequência.

## O que ainda falta (em aberto)

1. **Upload de áudio direto (voice notes de WhatsApp etc.).** O
   código já existe (`audio_file_input.py`, testado com Whisper
   simulado) — transcreve um arquivo ou vigia uma pasta, reaproveita
   o mesmo `WhisperModel` e o mesmo `DictationSession` do mic, sem
   mandar áudio bruto pra nenhuma IA (nenhuma delas aceita isso
   direto). Falta só chamar isso de dentro de `main.py` — hoje é uma
   peça solta, sem menu nem pasta configurada.
2. **Interface de configuração.** Hoje os comandos só são editáveis
   mexendo em `config.py`. Uma tela simples pra isso é o passo
   natural depois que a lógica estiver redonda.
3. **Multiplataforma de verdade.** A v1 é só Mac (rumps + AppleScript).
   `audio_input.py`, `command_router.py`, `dictation.py` e `config.py`
   já são portáveis — só `actions.py` e o wrapper de menu bar
   (`main.py`) precisariam de uma versão Windows.

Dois conceitos de design já existem em `design/` — mascote colorido
e uma versão monocromática pro ícone da barra de menu (ver
`design/DESIGN.md`). Ainda não reagido pela Valeta, então pode mudar
bastante antes de virar assets de verdade.


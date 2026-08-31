# vIsper — contexto do projeto

Este arquivo é lido automaticamente pelo Claude Code ao abrir esta
pasta. Ele existe pra você não precisar reconstruir o contexto do
zero — leia isso inteiro antes de mexer em qualquer coisa.

## O que é o vIsper

vIsper é um launcher ativado por voz pra IAs de chat (Claude, Claude
Code, ChatGPT, Perplexity, Gemini), pensado pra ser usado sem
encostar no teclado — a Valeta fala, o app abre a IA certa, escuta o
que ela dita, e manda pro chat sozinho.

Fluxo completo:
1. Ela fala a wake word (padrão: "vIsper") + o nome de uma IA — ex:
   "vIsper, claude". Isso abre o chat daquela IA.
2. Só a wake word sozinha, sem nome de IA reconhecível depois, abre a
   IA padrão (`config.DEFAULT_AI`).
3. A partir daí, tudo que ela falar é acumulado como ditado.
4. Quando ela fala a wake word de novo (mais qualquer palavra depois
   dela, não precisa ser uma frase específica tipo "terminei") — o
   texto acumulado é colado no campo de chat e o Enter é apertado
   sozinho ("manda ver").

Duas superfícies, ligadas uma à outra:
- **Mac** (`main.py` + módulos): app de barra de menu (rumps) que
  escuta o microfone, roda tudo isso, e executa a automação de
  verdade (abrir apps, colar texto, apertar Enter via AppleScript/
  System Events).
- **iPhone** (`ios/`): não repete a automação sozinho — só *aciona* o
  Mac remotamente (o porquê está em "Decisões de arquitetura" abaixo).
  Pensado pro caso de uso real de disparar um comando estando longe
  de casa, ex. durante o treino.

Entrada de áudio no Mac: qualquer microfone que o macOS reconheça.
Dois jeitos já detectados automaticamente, em ordem de prioridade via
`config.PREFERRED_INPUT_DEVICES` — DJI Mic (USB, não precisa do app
da DJI) e fone Bluetooth (a Valeta usa Sony WH-1000XM5; WF-1000XM5
também reconhecido) — mais qualquer outro escolhido manualmente no
menu. Ver "Sobre usar fone de ouvido" no README pro aviso de
qualidade de áudio ao usar Bluetooth (efeito colateral do protocolo,
não bug daqui).

## Decisões de arquitetura já tomadas (não revisitar sem motivo forte)

- **Automação via AppleScript/System Events** (clipboard + Cmd+V
  simulado + Enter simulado), controlando o navegador/apps já
  instalados — em vez de um cliente de chat nativo multi-provedor via
  API. Motivo: zero custo extra (reaproveita as assinaturas que já
  existem) e o mínimo de atrito possível — as duas prioridades de
  qualquer decisão de arquitetura neste projeto. Confirmado por
  pesquisa: nenhum produto de chat de IA aceita áudio bruto direto
  via API/web, sempre precisa transcrever pra texto primeiro — o que
  o pipeline Whisper já faz de qualquer forma.
- Prioridade de correspondência de trigger de IA: ganha o apelido que
  aparece PRIMEIRO na fala; empate na mesma posição vai pro mais
  COMPRIDO (`command_router.py`). As duas metades da regra vêm de bugs
  reais, corrigidos: o desempate por comprimento evita "claude" casar
  como substring de "claude code" antes de "claude code" ter chance de
  ganhar; e ordenar por POSIÇÃO antes disso evita o inverso — quando
  era só "o mais comprido primeiro", qualquer frase que citasse uma
  segunda IA depois abria a errada ("vIsper claude e não o perplexity"
  abria o Perplexity, porque 10 letras ganhavam de 6, e ainda jogava
  fora a fala inteira junto).
- **Detecção tolerante a erro de transcrição SÓ na abertura; o
  fechamento é sempre exato.** Motivo da assimetria: falso positivo ao
  ABRIR abre uma aba à toa (chato, recuperável); falso positivo ao
  FECHAR manda a mensagem pela metade (destrutivo). E falso NEGATIVO ao
  abrir era o pior problema real do app — "vIsper" é palavra inventada,
  o Whisper transcreve "whisper"/"vesper", "claude" falado em PT vira
  "cloud"/"clode", e cada erro desses fazia o comando falhar CALADO (o
  app parecia surdo). Duas camadas, complementares:
  (1) `hotwords` do faster-whisper (`config.transcription_hotwords()`,
  usado em `main._listen_loop_whisper`) — o vocabulário de comando
  entra como prioridade na decodificação, o erro acontece MENOS; o
  parâmetro foi conferido no fonte da wheel 1.0.3 pinada, não de
  memória. (2) casamento aproximado (`text_utils.find_trigger_span`,
  `difflib`, limiar `config.FUZZY_MATCH_THRESHOLD = 0.72`) — MEDIDO,
  não chutado: pega "whisper"(0.77)/"vesper"(0.83)/"cloud"(0.73)/
  "claudio"(0.77) e rejeita as palavras de ditado mais próximas
  ("dispersar" 0.67, "sempre" 0.50). Duas regras que mantêm isso
  seguro e que NÃO podem ser relaxadas sem repensar tudo: (a) gatilho
  de VÁRIAS palavras casa palavra-a-palavra pelo ELO MAIS FRACO — a
  primeira versão comparava a janela emendada e "claude não esqueça"
  virava "claude code" com 0.76, porque o "claude" compartilhado
  dominava a conta; (b) wake word (mesmo aproximada) + conteúdo depois
  mas NENHUM nome de IA continua dando None — é o que impede "véspera"
  no meio de conversa ambiente de disparar qualquer coisa. Palavras
  com menos de 4 letras nunca casam por aproximação. difflib (stdlib)
  em vez de rapidfuzz de propósito: são ~10 palavras curtas por chunk,
  performance é irrelevante, e uma dependência nativa nova arriscaria
  o build do .app que acabou de ficar verde.
- **`TRANSCRIPTION_LANGUAGES` é uma LISTA de idiomas permitidos
  (padrão `["pt", "en"]`), não um idioma único forçado.** Vem
  direto do relato dela: "eu quero falar em portugues e inglês, e
  aparetmente só funciona ingles". Causa real, achada testando: com
  `language=None`, os chunks de 4s (`AudioStream.chunks()`) às vezes
  são CURTOS DEMAIS pra detecção de idioma do Whisper ser confiável —
  limitação documentada do próprio modelo (viés conhecido pra inglês
  em áudio curto/ambíguo), não bug daqui. E o detalhe que torna isso
  grave: o Whisper transcreve NO idioma que ele achou, então detecção
  errada vira TEXTO errado, não só rótulo errado — português falado
  sai como inglês inventado. As três formas, todas configuráveis por
  `setup_visper.py` sem abrir arquivo `.py`:
  - **um idioma só** (`["pt"]`) — pula a adivinhação por completo,
    é o mais confiável de todos;
  - **vários** (`["pt", "en"]`, o padrão) — deixa detectar, mas SÓ
    aceita o palpite se ele estiver na lista E vier com confiança
    `>= config.LANGUAGE_CONFIDENCE_THRESHOLD` (0.5); senão
    RE-TRANSCREVE forçando o último idioma que passou nesse crivo
    (`self._last_good_language`), caindo no primeiro da lista se
    ainda não houve nenhum. Re-transcrever custa um segundo passe no
    MESMO chunk já em memória — barato perto de mandar texto errado
    pro chat;
  - **lista vazia** (`[]`, "auto") — sem restrição, aceita o erro de
    detecção junto.
  Pra diagnosticar sem precisar adivinhar: o idioma aparece no
  "Heard:" (`"[pt] oi tudo bem"`), e quando houve correção ele mostra
  as duas pontas (`"[en→pt] ..."`) — separa "o Whisper não ouviu" de
  "ouviu certo mas cravou o idioma errado" de "cravou errado e eu
  corrigi".
- **iPhone precisa ser um app separado que aciona o Mac, não que
  repete a automação sozinho** — iOS não deixa um app simular teclado
  dentro de outro app (sandbox). Não existe "AppleScript do iOS".
- **Relay via `ntfy` em vez de servidor só-na-rede-local** — a Valeta
  quer usar o iPhone mesmo fora da Wi-Fi de casa (ex. no treino). Um
  servidor só na rede local do Mac fica inalcançável assim que o
  iPhone troca de rede, não importa se o app já estava aberto antes
  de sair. `ntfy` é grátis, open-source, e funciona de qualquer lugar
  com internet — o Mac fica inscrito num tópico privado, o iPhone
  publica nesse tópico de onde estiver. **Segurança**: tópicos do
  ntfy.sh são públicos por padrão (sem senha) — o nome do tópico
  PRECISA ser uma string longa e aleatória, nunca algo óbvio, porque
  isso aciona automação de verdade no Mac.
- **Porcupine pra wake-word acústica, com arquitetura própria pra
  evitar dois motores pesados concorrentes.** A v1 (ainda o padrão)
  transcreve tudo continuamente com Whisper e procura a wake word no
  texto — funciona, mas gasta mais CPU e tem mais falso positivo/
  negativo. A tentativa óbvia de integrar o Porcupine (rodar ele E o
  Whisper contínuo ao mesmo tempo o tempo todo) foi propositalmente
  EVITADA por ser arriscada demais pra escrever sem hardware real pra
  testar. Em vez disso, `porcupine_session.py` alterna entre "só
  Porcupine" (ocioso, barato, frames pequenos) e "acumula áudio bruto
  + Porcupine no mesmo loop" (ditando) — só transcreve de verdade nos
  dois momentos que precisa (nome da IA logo após abrir; conteúdo
  completo no fechamento). Isso evita concorrência real sem abrir mão
  do ganho principal do Porcupine.
- **UI do produto em inglês.** Comentário de código e documentação
  deste projeto continuam em português (é como a Valeta se comunica
  aqui), mas qualquer texto que apareça DE VERDADE na interface do
  app (labels, botões, status) deve ser em inglês — pedido explícito
  dela, ver `design/layouts_mockup.html` como referência de como isso
  fica.
- **Cor de marca separada de cor de status.** Lavanda/mint são cores
  de MARCA (mascote, botões, fundo) — não usar pra comunicar estado.
  Estados usam uma paleta semântica própria: cinza (Idle), verde
  (Listening/Connected), âmbar (Connecting), vermelho-coral
  (Dictating), azul (Sent), terracota (Offline). Ver
  `design/layouts_mockup.html` pros valores hex exatos.
- **Detecção de microfone por lista de prioridade, não hardcoded pra
  uma marca só** (`config.PREFERRED_INPUT_DEVICES`, usado por
  `audio_input.guess_preferred_device()`). Cada grupo é
  `{"keywords": [...], "bluetooth": bool}`; o primeiro grupo que bater
  com um dispositivo conectado ganha. DJI Mic vem antes do fone
  Bluetooth de propósito — mic dedicado, sem o efeito colateral de
  qualidade abaixo. A flag `bluetooth` é o que decide se o aviso de
  qualidade aparece, então generaliza pra qualquer fone que a Valeta
  adicionar depois, não só o Sony XM5 de hoje. **Não voltar a
  hardcodar detecção pra um dispositivo só** — o padrão de lista
  existe justamente pra próximo mic/fone ser uma linha em
  `config.py`, não uma mudança de código.
- **Qualidade de áudio do sistema cai (mono, perfil HFP/HSP) enquanto
  o mic de um fone Bluetooth estiver em uso — aceito como custo
  conhecido, não um bug a "consertar".** É como o Bluetooth clássico
  funciona (troca de perfil A2DP↔HFP é decisão do SO, não controlável
  pelo app); a única mitigação real seria não manter o stream de
  entrada aberto o tempo todo, o que hoje conflita com o modo Whisper
  contínuo (que precisa escutar sem parar pra pegar a wake word). O
  vIsper só avisa (notificação, uma vez por sessão de escuta) — ver
  README pro texto exato do aviso.
- **Vocabulário de fechamento: "câmbio" (PT) / "over" (EN), além da
  wake word.** Analisei palavras candidatas pelos dois critérios que
  importam: soam naturais pro que fazem, E são raras o bastante em
  fala natural pra não disparar por acidente no meio de um ditado
  comprido. Palavras óbvias tipo "manda"/"send", "pronto"/"done",
  "beleza" foram descartadas por serem comuns demais no dia a dia —
  arriscam fechar cedo se aparecerem organicamente na frase que você
  está ditando. "câmbio"/"over" vêm do vocabulário de comunicação por
  rádio ("terminei de falar, sua vez") — o sentido bate exatamente
  com a ação, e nenhum dos dois é uma palavra do dia a dia. Isso só
  funciona bem porque o casamento é por PALAVRA INTEIRA
  (`text_utils.py`, `contains_word()`), não substring — sem isso,
  "over" casaria dentro de "however"/"moreover"/"discover"/"cover",
  que são comuns em qualquer ditado em inglês. `text_utils.py`
  também dobra acento (câmbio/cambio contam igual), pra tolerar o
  Whisper transcrever com ou sem acento.
- **Cancelar exige ADJACÊNCIA à wake word ("vIsper, cancela"), não só
  a palavra em algum lugar do trecho.** O ditado só tinha uma saída, e
  ela era a destrutiva: mandar. Transcrição erra, então precisava
  existir um jeito de desistir sem matar o app —
  `config.CANCEL_TRIGGERS` (`cancela`, `cancelar`, `cancel`,
  `esquece`, `forget it`) resolvido por
  `dictation._is_cancel()`. Mas essas palavras são o OPOSTO de
  "câmbio"/"over": são comuns em fala normal. Bastar a palavra em
  qualquer lugar do trecho faria "preciso cancelar a reserva, vIsper"
  (fechar um ditado que por acaso fala em cancelar) APAGAR tudo em vez
  de mandar — o oposto exato do pedido, e irreversível. Por isso a
  regra é `text_utils.starts_with_word()` sobre o que vem DEPOIS da
  wake word: essa frase manda normalmente, e só o comando de verdade
  cancela. Dois detalhes que não podem ser mexidos sem repensar tudo:
  (a) o cancelamento é checado ANTES do fechamento, nas DUAS pontas
  (no trecho que fecha e no `leftover` do que abre) — "vIsper cancela"
  contém a wake word, que também é gatilho de fechamento, então na
  ordem errada pedir pra cancelar MANDARIA; (b) o som do cancelamento
  (`config.DICTATION_CANCEL_SOUND`, callback `on_cancel`) é DIFERENTE
  do de mandar de propósito — sem sinal distinto não dá pra saber se o
  texto foi embora ou foi descartado, que é justamente a dúvida que o
  cancelamento existe pra tirar. Casamento EXATO, sem tolerância a
  erro de transcrição, mesma regra do fechamento e pelo mesmo motivo:
  os dois desfechos são irreversíveis.

- **"Recent activity…": as últimas 25 linhas de "ouvi X / decidi Y",
  só na MEMÓRIA.** O "Heard:" do menu responde "ele está me ouvindo
  agora?", mas não responde a pergunta que aparece de verdade num teste
  real: "falei o comando faz 30 segundos e não aconteceu nada — o que
  ele entendeu?". Quando ela abre o menu pra olhar, o trecho que
  interessa já foi sobrescrito (chega um novo a cada ~4s) e cortado em
  45 caracteres — justamente o fim da frase, que é onde mora o gatilho
  de fechamento. E o outro retorno, `notify()`, some em segundos e é
  no-op rodando por `python3 main.py`. Ou seja: no momento do
  diagnóstico não sobrava evidência nenhuma — foi exatamente a situação
  que produziu "nao funciou o comando de voz" sem mais detalhe, e
  custou uma ida e volta inteira pra descobrir a causa. Duas metades
  são guardadas SEPARADAS, o que foi OUVIDO e o que foi DECIDIDO,
  porque a falha mais comum é as duas não combinarem (ouviu certo e
  roteou errado, ou não ouviu). **Nunca em disco, de propósito**: o app
  escuta o tempo todo, então gravar transcrição em arquivo seria uma
  mudança de privacidade que ninguém pediu — e é desnecessária, já que
  a dúvida é sempre sobre o passado recente. `deque(maxlen=...)` sem
  lock: append/list são atômicos no CPython, o pior caso é uma linha
  fora de ordem (irrelevante pra diagnóstico) e segurar lock dentro do
  laço de transcrição seria pior. O teto é BAIXO (25) porque a janela é
  um `NSAlert` (`rumps.alert()`), que cresce junto com o texto e não
  rola — 40 linhas compridas renderiam um alerta mais alto que a tela,
  inútil justamente na hora de ler. E linha comprida é encurtada NO
  MEIO, nunca no fim (`_elide()`): as duas pontas de uma linha `heard`
  são os dois pontos de diagnóstico — a wake word abre a frase, o
  gatilho de fechamento ("over"/"câmbio") fecha —, então cortar o fim
  jogaria fora justamente a metade que explica por que o ditado não foi
  mandado. `_log_activity()` NÃO passa por
  `AppHelper.callAfter` — a regra da thread principal vale pra mutação
  de UI, e aqui não há nenhuma. Trecho silencioso não entra (senão o
  silêncio consumiria as 25 linhas e empurraria pra fora justamente o
  comando que falhou). 11 testes.
- **Toda string que `DictationSession.handle()` devolve é UI de
  produto, então está em INGLÊS.** Elas iam direto pro `notify()` (uma
  notificação do macOS — interface, não log interno) e agora aparecem
  também em "Recent activity…", mas estavam em português: "abriu
  claude — ouvindo ditado", "ditando…", "mandou: …". Contrariava a
  decisão de UI em inglês registrada aqui, e era o único lugar do app
  onde isso ainda acontecia. A tradução consertou junto uma ambiguidade
  real criada quando "vIsper, cancela" foi acrescentado: DOIS desfechos
  diferentes diziam "cancelado" — o cancelamento de verdade e o
  fechamento sem nada no buffer. Hoje são `"cancelled — …"` e
  `"nothing to send — the dictation was empty"`, que é a diferença que
  importa (um jogou fora o que você ditou; o outro não tinha nada pra
  jogar). Os marcadores dos testes (`"abriu_claude"`, `"mandou_enter"`)
  continuam em português de propósito — são fixture de teste, não UI.

- **Configuração pessoal mora FORA do repositório**
  (`user_settings.py` → `~/Library/Application Support/vIsper/settings.json`).
  O repo é PÚBLICO e o `NTFY_TOPIC` é, na prática, a senha que impede
  qualquer pessoa do mundo de disparar automação real no Mac dela. O
  README antigo mandava colar isso no `config.py`, que é versionado —
  um `git push` distraído publicaria a chave da casa. Hoje `config.py`
  só tem PADRÕES e documenta cada opção; `apply_overrides(globals())`
  na ÚLTIMA linha sobrepõe o que houver no settings.json, então nenhum
  outro módulo precisou mudar (quem faz `from config import X` recebe o
  valor final sem saber que houve sobreposição). Valor com tipo errado
  é descartado SOZINHO, sem levar o arquivo junto; arquivo quebrado
  nunca derruba o app (num `.app` não há Terminal pra mostrar o erro).
  `check_no_secrets.py` roda no CI e falha se algum segredo voltar pro
  `config.py`. Efeito colateral que resolve o pedido de distribuir pra
  outras pessoas: cada uma tem a sua config, e `git pull` nunca
  conflita com ela.
- **O ícone da barra de menu É o estado** (`main.STATUS_ICONS`:
  carregando/parado/escutando/ditando/mandou/erro). Antes o título era
  fixo e o único retorno era notificação, que some sozinha em segundos
  — não dava pra responder a pergunta mais básica ("ele está me
  ouvindo agora?") sem falar uma frase de teste e torcer.
  **Já passou por TRÊS versões, e cada uma consertou o que a anterior
  quebrou — a lição que vale registrar é que FORMA e COR são dois
  eixos separados e acertar um não vale sacrificar o outro:**
  (1) EMOJI (⏳🎙🟢🔴🔵🟠) como texto do título — funcionava, mas a
  Valeta testou de verdade e apontou que "as cores que você falou não
  estão funcionando": emoji usa as cores do FONTE da Apple, não as da
  paleta semântica documentada (🟠 não é terracota; 🎙 não tem cor de
  estado nenhuma). (2) CÍRCULO colorido sólido — cor certa, mas jogou
  a identidade fora, e a resposta dela foi "os ícones deveriam seguir
  o briefing inicial". (3) A SILHUETA DO MASCOTE na cor do estado
  (atual): a forma é a MESMA de `design/menubar_icon_template.svg` (o
  briefing) e nunca muda, porque é o que identifica o vIsper na
  barra; a cor é a paleta semântica, e é só ela que muda com o estado.
  Os PNGs (`status_icons/*.png`) saem de
  `design/generate_status_icons.py`, escrito com zlib+struct puro —
  sem Pillow, sem cairosvg, sem dependência nova só pra 6 imagens
  pequenas. Como não dá pra "importar" um SVG sem dependência, as
  primitivas do briefing estão TRANSCRITAS em `SHAPES` com os números
  literais do arquivo (mexeu no SVG, mexe lá e rode de novo), e são
  rasterizadas por distância com sinal — é o que dá antialiasing de
  graça sem biblioteca gráfica. `test_status_icons.py` fecha os dois
  círculos contra os BYTES do PNG: a cor contra o hex de
  `layouts_mockup.html`, e pontos do desenho contra a geometria de
  `menubar_icon_template.svg` — inclusive o VÃO entre as duas antenas,
  que é justamente o ponto onde um círculo teria tinta e o mascote
  não tem. O PNG precisa ser QUADRADO: o rumps fixa a imagem em 20×20
  pontos (`image.setSize_((20, 20))`, sem como passar outro valor pela
  propriedade `.icon`), então imagem não-quadrada sairia espremida. **Sem `template=True`** (rumps.App.icon,
  parâmetro `template`) de propósito: template forçaria monocromático
  conforme claro/escuro, apagando a cor de novo pelo mesmo motivo do
  emoji, só que por outro caminho — conferido no source do rumps
  0.4.0 (`_nsimage_from_file`, `image.setTemplate_`), não de memória.
  `setup.py` leva `status_icons/` pro bundle via `DATA_FILES`
  explícito — carregado por CAMINHO de arquivo (`rumps.App.icon`
  exige path, não aceita bytes/NSImage direto), então py2app não
  rastreia essa dependência sozinho só seguindo imports.
- **Toda mutação de AppKit vinda de thread de FUNDO passa por
  `AppHelper.callAfter`** (`PyObjCTools.AppHelper`, já vem com
  `pyobjc-framework-Cocoa` — dependência do próprio rumps, nada novo
  pra instalar). **Crash real, achado testando de verdade** (não
  suposição): `EXC_BREAKPOINT`/`SIGTRAP`, "Must only be used from the
  main thread", bem no meio de `popUpStatusBarMenu` — a Valeta tinha o
  menu ABERTO no exato momento em que uma thread de fundo
  (`_load_model`, `_listen_loop_*`, ou `_on_result` vindo do relay do
  iPhone) tentava trocar o ícone ou o texto do "Heard:". AppKit não é
  thread-safe pra mutação de UI — regra do próprio Apple, não bug do
  rumps nem do PyObjC. Sistemática: qualquer `self.icon = ...`,
  `self.<MenuItem>.title = ...`, ou `rumps.alert()` (cria `NSAlert` e
  chama `runModal()` — MESMA exigência de main thread, achado
  revendo TODOS os call sites depois do crash, não só o que apareceu
  no relatório) chamado de fora de um `@rumps.clicked` (que já roda na
  main thread) PRECISA passar por `AppHelper.callAfter`.
  `rumps.notification()` é a ÚNICA exceção conferida — usa
  `NSUserNotificationCenter`, que a Apple documenta como thread-safe
  pra postar (`notify()` continua chamado direto de qualquer thread).
  Rastreamos o estado LÓGICO num atributo Python simples
  (`self._current_state`, atualizado SINCRONAMENTE) em vez de reler
  `self.icon`/`self.title` depois de mudar: a mutação real do AppKit
  via `callAfter` é ASSÍNCRONA (só acontece no próximo ciclo do
  runloop principal), então reler a propriedade logo em seguida podia
  pegar o valor ANTIGO — foi exatamente esse padrão que
  `_on_result()` usava antes (`self.title != STATE_GLYPHS["sent"]`) e
  precisou ser trocado. Dublê de teste (`test_main.py`,
  `PyObjCTools.AppHelper` fake) executa o callback NA HORA — suficiente
  pra testar o QUE seria chamado e COM QUE argumento, mas a entrega
  assíncrona de verdade continua só validável num Mac.
- **O modelo do Whisper carrega em THREAD, nunca no `__init__`.**
  São ~150 MB baixados na primeira execução: no `__init__` o app ficava
  minutos sem ícone nenhum, e qualquer falha matava o processo ANTES do
  ícone existir. Regra geral que vale pra qualquer coisa nova no
  `__init__`: **nada que possa demorar ou levantar exceção pode rodar
  antes do ícone aparecer** — sem Terminal, um app que morre ali não
  deixa rastro em lugar nenhum.
- **Fallback pro microfone padrão do sistema**
  (`audio_input.default_input_device()`). `guess_preferred_device()` só
  conhece DJI e Sony; sem nenhum dos dois plugado ela devolvia None e
  "Start listening" só mostrava um alerta — quem abrisse o app sem o
  mic específico concluiria que ele não funciona, com o microfone do
  MacBook ali o tempo todo.
- **O relay do iPhone não pode abrir `claude_code`**
  (`config.RELAY_BLOCKED_AIS`). Abrir o Claude Code roda um AppleScript
  que abre o Terminal e DIGITA nele. Pelo mic local isso é ótimo (você
  está na frente da máquina); vindo do ntfy, vazar o tópico deixa de
  ser "conseguir digitar num chat" e vira execução de comando. A
  checagem usa `CommandRouter.preview()`, que reusa o MESMO `_decide()`
  de `route()` — um filtro com lógica paralela divergiria do roteador e
  acabaria liberando justamente o que deveria barrar.
- **`rumps.notification()` nunca é chamado direto — sempre por
  `main.notify()`.** Ele exige bundle com identificador e levanta
  `RuntimeError` rodando por `python3 main.py`, que é exatamente como o
  primeiro teste acontece. Chamado de dentro do loop de ditado, isso
  derrubava a thread de escuta inteira: o app parava de funcionar por
  causa do MECANISMO DE AVISO, não do que ele avisa.
- **`vad_filter=True` na transcrição.** Sem ele o Whisper ALUCINA em
  cima de silêncio (costuma devolver "Legendas pela comunidade
  Amara.org" e afins, resquício do treino em vídeo legendado). Num app
  que escuta o tempo todo isso não é detalhe: texto inventado entra no
  ditado como fala real, e uma alucinação que contenha a wake word ou
  "over" dispara ação sozinha.
- **O DMG é compilado pelo GitHub Actions num macOS de verdade**, não
  na máquina dela. Sem isso, ter o DMG exigia venv + pip + Homebrew
  funcionando primeiro — exatamente o atrito que o app deveria
  eliminar. Runner macOS é grátis e ilimitado em repo público. Efeito
  colateral igualmente importante: é o primeiro lugar onde o
  empacotamento roda num macOS real, e o smoke test (abre o bundle,
  confere que sobrevive 20s) pega justamente a falha silenciosa do
  py2app quando falta lib nativa.
- **No iPhone, o que dispara o envio automático é OCIOSIDADE de
  digitação, não o fim do reconhecimento de voz.** Pedido literal
  dela: "eu não quero ter que apertar enviar para o mac". A primeira
  versão só mandava sozinho no `onend` do Web Speech API — e o Web
  Speech API é justamente a peça que NÃO dá pra contar no iOS: quando
  ele falta, `speechSupported()` desabilita o botão de microfone e
  sobrava digitar + apertar "Send to Mac" na mão, exatamente o toque
  que não deveria existir. Hoje qualquer evento `input` no campo (a
  tecla de MICROFONE do teclado do próprio iPhone dispara esse evento
  igual a digitar) arma um timer de `IDLE_MS = 2500`; parou de mexer,
  começa a MESMA contagem de 3s com a MESMA janela de cancelamento.
  Total: 5,5s de silêncio antes de sair. Três regras que vieram de
  pensar nos casos ruins: (a) mexer no texto durante a contagem
  cancela E rearma — senão "corrigi uma letra" viraria "agora tem que
  apertar enviar na mão"; (b) cancelar DE PROPÓSITO (tocar no botão,
  que durante a contagem vira "Tap to cancel") desarma a ociosidade
  também, senão a contagem voltaria sozinha em 2,5s e o toque não
  teria servido pra nada; (c) desligar o ajuste nas configurações
  desarma o que já estava armado, não só o próximo.
- **Bug real achado por causa disso, que vale registrar: `hidden` é
  propriedade de `HTMLElement`, e `SVGElement` NÃO herda dela.**
  `ring.hidden = false` (o anel de contagem é um `<svg>`) só criava
  uma propriedade JS solta — o atributo `hidden` continuava no
  elemento, e a regra `.countdown svg.ring[hidden] { display: none }`
  mantinha o anel invisível DURANTE a contagem inteira. Ou seja: o
  único sinal visual de "vai mandar, toca pra cancelar" nunca
  apareceu. É a SEGUNDA mordida do mesmo detalhe de SVG — aquela
  regra de CSS existe justamente porque `hidden` não esconde SVG
  sozinho. Hoje usa `removeAttribute`/`setAttribute`, e
  `test_pwa.js` checa a visibilidade real do anel nos dois estados.
  Confirmado rodando no Chromium (`typeof svg.hidden === "undefined"`,
  `'hidden' in SVGElement.prototype === false`), não de memória.
- **O app de iPhone é um PWA no GitHub Pages (`docs/`), não Swift.**
  iOS não instala app de arquivo; com conta grátis de desenvolvedor o
  app EXPIRA EM 7 DIAS, com conta paga são US$99/ano — as duas
  contrariam custo zero. O PWA vira ícone na tela de início pelo
  "Adicionar à Tela de Início", não expira, e é testado num Chromium de
  verdade a cada push (`test_pwa.js`), o que faz dele a peça MAIS
  validada do projeto. **Armadilha do iOS que já mordeu**: o app da
  tela de início tem armazenamento SEPARADO do Safari — o que atravessa
  é a URL do atalho, então o fragmento `#t=<tópico>` só pode ser
  apagado DEPOIS de já estar rodando em modo standalone, e o manifest
  não pode definir `start_url` (com ele o iOS guardaria a URL do
  manifest e jogaria o hash fora do mesmo jeito).

## Estado atual do código

Todo o código Python foi escrito e testado neste ambiente (sandbox
Linux, sem Mac, sem mic, sem Xcode) — **nada rodou numa máquina real
ainda**. "Testado" abaixo sempre quer dizer testes unitários com
tudo que precisa de hardware real simulado (mocks). Isso não
substitui testar de verdade — é só o que dava pra garantir sem
hardware.

Módulos principais (mic local, sempre ativos):
- `config.py` — wake word, IA padrão, apelidos de cada IA, palavras
  de fechamento (`CLOSE_TRIGGERS`), dispositivos de entrada preferidos
  (`PREFERRED_INPUT_DEVICES` — DJI Mic, Sony XM5), tópico do ntfy,
  chaves do Porcupine. É o arquivo que se edita pra ajustar
  comportamento sem mexer no resto.
- `text_utils.py` — comparação de texto compartilhada entre
  `command_router.py` e `dictation.py`: casa por PALAVRA INTEIRA (não
  substring) e ignora acento. Existe especificamente porque "over"
  (um dos `CLOSE_TRIGGERS`) casaria dentro de "however"/"discover" se
  fosse substring simples. Duas famílias de função, com contratos BEM
  diferentes de propósito:
  - `split_after_word()` — resultado NUNCA é mostrado a ninguém, só
    comparado contra outro gatilho depois. Apara pontuação nas bordas
    (não só espaço) — sem isso, "vIsper." (Whisper adiciona ponto
    final com frequência) não abria a IA padrão, porque "." sobrava
    como se fosse conteúdo depois da wake word. Essa aparagem é por
    CATEGORIA Unicode (`_is_edge_char()`), não por uma lista fixa de
    caracteres ASCII: era `string.whitespace + string.punctuation`, e
    aí "vIsper—" (o Whisper transcreve travessão, reticências e aspas
    curvas de verdade) deixava "—" sobrando como conteúdo e a wake
    word sozinha simplesmente não abria a IA padrão — o mesmo bug do
    caso "vIsper.", só que pra pontuação não-ASCII.
  - `split_before_any()`/`text_after_word()` — resultado PODE virar
    conteúdo real colado no chat, então preservam capitalização/
    acento/pontuação REAL do original (ao contrário da família
    acima). **Cuidado que já mordeu uma vez**: a primeira versão de
    `split_before_any()` reusava a mesma lista de caracteres de borda
    de `split_after_word()` (espaço + pontuação) — isso apagava "!"/
    "?"/"." de VERDADE no fim de frases reais ditadas. Corrigido pra
    aparar só espaço nas bordas. `text_after_word()` tem uma
    assimetria de propósito: apara pontuação da borda ESQUERDA (logo
    depois da palavra-gatilho, tipo "claude," — sempre artefato de
    como a palavra foi dita) mas só espaço da borda DIREITA (pode ser
    fim de frase real, tipo "...tempo hoje?").
    **Cuidado que mordeu de novo, e pior**: essas duas acham o gatilho
    no texto DOBRADO (minúsculo/sem acento) e fatiam o texto ORIGINAL
    com esse índice. Isso pressupunha que dobrar preserva o
    comprimento — e não preserva: `fold_accents()` usa NFKD, que é
    decomposição de COMPATIBILIDADE, então "…" vira "..." (+2) e
    ligaduras tipo "ﬁ" viram "fi" (+1). O resultado era texto
    corrompido colado direto no chat da IA ("Bom dia… over" virava
    "Bom dia… ov"; "vIsper… claude qual é..." virava "ual é..."). Hoje
    `_fold_with_index_map()` guarda, pra cada caractere do texto
    dobrado, de qual posição do original ele veio — **qualquer função
    nova que ache posição no dobrado e fatie o original TEM que usar
    esse mapa**. `starts_with_word()` é a mais nova antes desta leva, e
    existe só pra o cancelamento poder exigir ADJACÊNCIA à wake word —
    ver a decisão sobre cancelar acima.
  - `strip_trailing_word()` — a mais nova. Diferente das duas famílias
    acima: procura o gatilho SÓ NO FIM do texto (não em qualquer
    lugar), e existe especificamente pro relay do iPhone (ver
    `dictation.handle_complete()` e a decisão de arquitetura
    correspondente) — o app de iPhone gruda um "over" fixo no FIM de
    TODA mensagem só pra sinalizar "isto é tudo", não como parte do
    que a pessoa quis dizer, então achar a PRIMEIRA ocorrência
    (`split_before_any`, certo pra mic) cortaria cedo demais qualquer
    conteúdo que legitimamente contivesse "over"/"câmbio" antes do
    marcador. Casando só a partir do fim, "let's talk this over" +
    marcador vira "let's talk this over over" → remove só o ÚLTIMO,
    preservando o "over" de verdade da frase. 66 testes.
- `audio_input.py` — lista/detecta microfones (`guess_preferred_device()`,
  `classify_device()`, orientados por `config.PREFERRED_INPUT_DEVICES` —
  casamento por SUBSTRING simples, não palavra inteira, porque nome de
  hardware não é fala) e captura áudio em dois formatos diferentes:
  `chunks()` (blocos de segundos, float32, pro Whisper) e
  `raw_frames()` (frames pequenos e fixos, int16, pro Porcupine).
  `resolve_device_by_name()` existe pra re-resolver uma escolha MANUAL
  pelo nome a cada uso, em vez de confiar num índice guardado — índice
  do sounddevice é posicional, não estável (pode reindexar quando
  outro dispositivo conecta/desconecta). `load_saved_device_name()`/
  `save_device_choice()` persistem essa escolha manual entre execuções
  em `~/Library/Application Support/vIsper/device.json` (só o NOME,
  nunca índice) — falha ao ler/escrever (disco cheio, corrompido etc.)
  é engolida de propósito, isso é conveniência, não deve impedir o app
  de funcionar. `label_devices()` desambigua o RÓTULO exibido no
  submenu quando dois dispositivos têm o MESMO nome (rumps indexa
  submenu por título — sem isso o segundo simplesmente sumia do menu);
  seleção/persistência continuam usando o nome puro, não o rótulo
  (limitação aceita pro caso de dois dispositivos IDÊNTICOS, ver
  "Limitações conhecidas"). 28 testes (`test_audio_input.py`) — cobrem
  detecção por nome (mockando `sd.query_devices()`) e persistência
  (apontando `DEVICE_STATE_PATH` pra um diretório temporário, nunca o
  real); nunca abre stream de verdade. Arquivo de teste cai pra um
  dublê de `sounddevice` se a lib nativa PortAudio não estiver
  instalada, pra rodar em qualquer sandbox.
- `command_router.py` — decide qual IA abrir a partir do texto
  transcrito, usando `text_utils.py`. `route()` retorna
  `(nome_da_ia, leftover)`, não só o nome — `leftover` é o que sobrou
  depois do nome da IA (ou "" se foi só a wake word, abrindo
  DEFAULT_AI), com capitalização/acento/pontuação REAL preservados
  (`text_utils.text_after_word()`) — resgata conteúdo dito na MESMA
  respiração que o comando de abrir (ex.: "vIsper claude qual é a
  previsão do tempo" tudo de uma vez, sem pausa), simétrico à correção
  equivalente já feita do lado do FECHAMENTO em `dictation.py`. Mudar
  esse contrato (de string solta pra tupla) exigiu atualizar os 7
  testes já existentes — mecânico, mas intencional: quem chamar
  `route()` de algum lugar novo precisa desempacotar a tupla, não
  tratar o retorno como string. A escolha da IA é por POSIÇÃO do
  apelido na fala (mais cedo ganha), com desempate por comprimento —
  ver o raciocínio e o bug que motivou cada metade em "Decisões de
  arquitetura". 24 testes dedicados.
- `dictation.py` — a máquina de estados ocioso/ditando. Fecha com a
  wake word OU qualquer `CLOSE_TRIGGERS`. A mensagem final é o BUFFER
  INTERNO (populado por chamadas anteriores de `.handle()`) **mais**
  qualquer conteúdo que veio ANTES do gatilho de fechamento no MESMO
  trecho que fechou (`text_utils.split_before_any()`) **mais**
  qualquer conteúdo que veio DEPOIS do nome da IA no MESMO trecho que
  abriu (`command_router.route()`'s `leftover`) — as duas pontas
  corrigidas depois que testes concretos mostraram que "terminar/
  começar a frase colado com o gatilho, sem pausa" descartava conteúdo
  de verdade em qualquer uma das duas. E o MESMO trecho pode abrir e
  fechar de uma vez ("vIsper claude qual é a previsão do tempo over",
  o pedido inteiro numa respiração só — o jeito mais natural de usar
  isso): o `leftover` da abertura passa pela mesma checagem de
  fechamento, senão o "over" ia pro buffer como se fosse conteúdo, o
  ditado ficava aberto pra sempre esperando um fechamento que já tinha
  sido dito, e a palavra "over" acabava colada no texto mandado pra
  IA. Ao integrar qualquer fonte de áudio nova, o que importa lembrar
  agora é que o texto da chamada que ABRE e o texto da chamada que
  FECHA podem os dois ter conteúdo real misturado com o gatilho — e
  podem até ser a MESMA chamada —, não só as chamadas do meio.
  `DictationSession` aceita `on_open`/`on_send`/`on_cancel`
  opcionais (callbacks sem argumento, só feedback — não afetam a
  máquina de estados; `on_send` NÃO dispara quando o fechamento não
  tinha nada pra mandar), usados por `main.py` pra tocar o earcon.
  **`handle_complete()`** é a segunda entrada pública, pro relay do
  iPhone (ver `relay_listener.py` e a decisão de arquitetura
  correspondente): ao contrário de `handle()`, o conteúdo só tem um
  gatilho removido se ele estiver GRUDADO NO FIM
  (`text_utils.strip_trailing_word()`), nunca procurado no meio —
  corrige um bug real de dados: o app de iPhone gruda " over" no fim
  de TODA mensagem por construção, então com `handle()` comum
  qualquer conteúdo ditado/digitado que já contivesse "over" (ex.:
  "let's talk this over") ou "câmbio" era TRUNCADO ali no meio, já
  colado E já com Enter apertado antes de alguém perceber — e o
  telefone mostrava "Sent to your Mac" de qualquer forma, porque o
  POST pro ntfy tinha sucesso mesmo quando o Mac mandou a mensagem
  pela metade. `self._lock` (`threading.RLock`) protege
  `dictating`/`buffer` porque `handle()`/`handle_complete()` rodam em
  THREADS diferentes sobre a MESMA sessão (mic e relay, ver
  `main.py`) — sem isso havia uma corrida de verdade: a checagem
  `not self.dictating` podia ser lida por AMBAS as threads antes de
  qualquer uma escrever `True`, porque no meio tem uma chamada
  BLOQUEANTE de verdade (`router.route()` → `subprocess.run()` abrindo
  o app) entre ler e escrever — janela larga o bastante pra um comando
  quase simultâneo pelo mic e pelo iPhone abrir DUAS IAs e perder o
  conteúdo de uma das duas. 42 testes dedicados (inclui um teste de 20
  threads concorrentes contra a mesma sessão, provando que o lock
  serializa sem perder/corromper conteúdo — não reproduz o timing
  exato da corrida original, isso exigiria hardware real, mas prova
  que o lock existe e funciona).
- `actions.py` — as ações de verdade (abrir app/URL, colar texto,
  apertar Enter) via `subprocess`/`osascript`. Todo `subprocess.run()`
  usa `check=True` — antes, uma falha (ex.: permissão de
  Acessibilidade ainda não concedida) fazia a ação simplesmente NÃO
  FAZER NADA, sem erro, sem log, sem jeito de saber o que aconteceu.
  Agora vira `CalledProcessError`, capturado por
  `main._listen_loop_safe` e avisado por notificação. `play_sound()` é
  a exceção de propósito: usa `Popen` (não-blocking) e ENGOLE falha —
  é earcon (`config.DICTATION_OPEN_SOUND`/`DICTATION_SEND_SOUND`), não
  pode travar o loop de ditado nem parecer que a ação real falhou. 18
  testes (`test_actions.py`, mockando `subprocess.run`/`Popen` —
  primeira cobertura deste arquivo).
- `main.py` — o app de barra de menu (rumps). Escolhe automaticamente
  entre dois caminhos de escuta: Whisper contínuo (padrão) ou
  Porcupine (`_listen_loop_porcupine`, só ativa com as duas chaves de
  Porcupine configuradas — **essa junção com hardware real nunca foi
  testada**, só a lógica de estados isolada). Submenu "Escolher
  microfone" agora é funcional de verdade (era só um alerta
  informativo antes): lista os dispositivos atuais (rótulo já
  desambiguado por `audio_input.label_devices()` se dois tiverem o
  mesmo nome), clicar num deles fixa a escolha manual E salva
  (`audio_input.save_device_choice()`, sobrevive a reiniciar o app),
  "Detectar automaticamente" volta a deixar `guess_preferred_device()`
  decidir a cada "Iniciar escuta" E esquece a escolha salva. Checkmark
  do submenu compara por NOME, não
  índice — importante pra mostrar certo logo no primeiro
  `_rebuild_mic_menu()` do `__init__`, antes de qualquer índice ter
  sido resolvido de verdade. Uma escolha manual RESTAURADA de outra
  execução é reclassificada pelo nome (`classify_device()`) no
  `__init__` e em `_resolve_device()` — só o NOME é persistido, então
  sem isso `device_is_bluetooth` voltava False ao reabrir o app e o
  aviso de qualidade Bluetooth nunca mais aparecia, justo no caso em
  que ele é mais útil (fone escolhido de propósito, sessão após
  sessão). "Iniciar escuta" tem dois guards, não um: `self.listening`
  E a thread anterior ainda viva — "Parar escuta" só baixa a flag, e a
  thread antiga pode continuar até `chunk_seconds` dentro de um
  `stream.read()`; sem o segundo guard, Parar seguido de Iniciar abria
  uma SEGUNDA thread de escuta, com duas transcrições paralelas
  alimentando o mesmo `DictationSession`. Thread de escuta envolvida
  em try/except (`_listen_loop_safe`) — sem isso, stream falhando ao
  abrir (ex.: fone Bluetooth desconectou) travava `self.listening=True`
  pra sempre, exigindo reiniciar o app. **Wake word, idiomas e tópico
  do iPhone se ajustam pelo MENU** ("Wake word…", "Spoken languages…",
  "iPhone connection…", todos por `_ask()` → `rumps.Window`), não só
  pelo `setup_visper.py` — quem instalou pelo `.dmg` não tem o
  repositório nem o script na máquina, e mandar essa pessoa editar o
  `config.py` é exatamente o atrito que o `.dmg` existe pra tirar.
  Idioma vale NA HORA (`_apply_languages()`, chamado tanto pelo
  `__init__` quanto pelo menu — as três derivadas mudam juntas); wake
  word exige reabrir, porque `dictation.py`/`command_router.py` leem
  `WAKE_WORD` uma vez na importação. **"Recent activity…"** mostra as
  últimas 25 linhas de "ouvi X / decidi Y" (`_log_activity()`,
  `_history`) — é a ferramenta de diagnóstico do teste manual, ver a
  decisão sobre ela acima. `_log_relay_received()` alimenta esse
  mesmo histórico com o marcador `"phone"` pra TODA mensagem que
  chegar do iPhone, mesmo quando ela não bater com nada — plugado como
  `on_message` na construção do `RelayListener`. Sem isso, uma wake
  word desatualizada no telefone (trocada no Mac pelo menu "Wake
  word…" sem atualizar o link salvo lá) fazia a mensagem chegar,
  não bater com nada, e sumir sem deixar rastro NENHUM — nem no
  "Heard:" (que é só do mic), nem em "Recent activity" — justo a
  ferramenta feita pra responder "por que não funcionou" ficava cega
  pra essa falha específica. `_on_result()` também ganhou um `else`
  que faltava: fechar um ditado do iPhone SEM conteúdo pra mandar
  (dictation.py's `_finalize()` pula `on_send()` nesse caso, de
  propósito) nunca disparava o único outro código que reverte o ícone
  — em uso só-pelo-iPhone (`self.listening == False` o tempo todo, o
  cenário principal do relay, longe de casa) o ícone ficava PRESO em
  "dictating" pra sempre depois disso, mesmo com o app inteiramente
  ocioso. O estado "mandou" é um
  FLASH (`_flash_state`, ~2,5s) e não um estado fixo: mandar é um
  evento e a escuta continua, então o azul ficava respondendo ERRADO
  a única pergunta que o ícone existe pra responder ("ele está me
  ouvindo agora?") até acontecer outra coisa — podiam ser minutos. O
  timer relê `_current_state` na hora de voltar em vez de capturar o
  estado de antes: entre o flash e o disparo dá tempo de parar a
  escuta, começar outro ditado ou dar erro, e nenhum desses pode ser
  desfeito por um timer velho. 86 testes
  (`test_main.py` — primeira cobertura deste arquivo; dubla `rumps`,
  `faster_whisper` e `sounddevice` pra rodar em sandbox, cobre escolha
  de dispositivo, os guards de "Iniciar escuta" e o checkmark do
  submenu; NÃO cobre nada de AppKit/áudio de verdade). **A API do
  rumps usada aqui
  (`MenuItem.clear()/.add()`, `.state`, `.title` mutável) foi
  conferida linha a linha contra o source real do pacote (baixado da
  PyPI, versão 0.4.0 — a mesma do `requirements.txt`), não escrita de
  memória** — mas a integração com o AppKit/NSMenu de verdade continua
  **nunca testada numa máquina real**, mesmo padrão de honestidade do
  resto deste arquivo.

Módulos de entrada alternativa (compartilham o mesmo
`DictationSession`, então "abrir pelo Mac", "abrir pelo iPhone" e
"abrir por um arquivo de áudio" nunca ficam em estados diferentes):
- `relay_listener.py` — escuta o tópico ntfy, alimenta o
  `DictationSession`. Já plugado em `main.py`. Backoff exponencial no
  reconnect (5s→10s→20s...até 60s, reseta ao reconectar) — aplicado a
  TODA reconexão, não só às que morreram com exceção: um stream que
  acaba limpo (ntfy reiniciou, proxy fechou por ociosidade) não
  levanta erro nenhum e antes caía direto no próximo `while`,
  reabrindo na hora, sem pausa — um servidor que aceitasse e fechasse
  na sequência virava um laço de requisições HTTPS a toda velocidade
  contra o ntfy.sh. Linha de JSON malformada pula só aquela linha, em
  vez de derrubar uma conexão que está funcionando. Chama
  `session.handle_complete()`, não `session.handle()` — ver a decisão
  de arquitetura sobre isso (mensagens do relay já chegam INTEIRAS,
  então não faz sentido vasculhar o meio do texto atrás de gatilho de
  fechamento). `on_message` opcional dispara com o texto BRUTO de
  TODA mensagem recebida, ANTES de qualquer trava ou tentativa de
  casar gatilho — plugado em `main._log_relay_received()`, existe
  porque sem isso uma mensagem que não bate com NADA (ex.: wake word
  desatualizada no telefone) não deixava rastro nenhum em "Recent
  activity", justo a ferramenta feita pra diagnosticar esse tipo de
  falha silenciosa. **Nunca testado contra o ntfy.sh de verdade** — o
  parsing foi conferido contra a documentação oficial do formato JSON
  deles, mas não contra uma conexão real.
- `wake_word_porcupine.py` — wrapper do motor Porcupine. Escrito
  contra a API real do pacote `pvporcupine` (conferida, não foi de
  memória). Não dá pra testar detecção de verdade sem AccessKey +
  arquivo `.ppn` reais.
- `porcupine_session.py` — a orquestração ocioso/ditando descrita
  acima. Já ligado em `main.py`. O fechamento entrega tudo numa
  chamada só a `DictationSession.handle()`, com a wake word emendada
  no fim do conteúdo transcrito. Isso já foram DUAS chamadas
  (conteúdo, depois wake word sozinha) e era um bug sério: o áudio da
  wake word de fechamento está DENTRO do buffer de ditado (o frame que
  dispara a detecção entra no buffer antes de ser processado), então o
  Whisper normalmente transcreve ela junto — a primeira chamada já
  fechava o ditado e a segunda caía numa sessão OCIOSA, onde wake word
  sozinha quer dizer "abre a IA padrão". Resultado: cada envio abria
  uma aba nova do Claude e deixava o app preso em modo ditado de novo.
- `audio_file_input.py` — transcreve um arquivo de áudio (voice notes
  etc.) ou vigia uma pasta. **Ainda não plugado em `main.py`** — sem
  menu nem forma de escolher a pasta ainda.

Configuração e distribuição (o que mudou o jeito de instalar):
- `user_settings.py` — a sobreposição pessoal descrita nas decisões
  acima. `load_settings()`/`save_settings()`/`apply_overrides()`, com um
  validador por chave (`VALIDATORS`). Valor inválido cai SOZINHO, sem
  levar o arquivo junto. `settings_path()` respeita a env var
  `VISPER_SETTINGS_PATH`, que é como os testes nunca tocam no arquivo
  real. 30 testes.
- `setup_visper.py` — assistente de primeira configuração. Só
  biblioteca padrão de propósito: a primeira coisa que a pessoa faz é
  ANTES de instalar qualquer dependência. Sorteia o tópico, e no fim
  imprime (e copia com `pbcopy`) o link do iPhone com o tópico no
  FRAGMENTO da URL — que navegador nenhum manda pro servidor, então
  não aparece em log do GitHub Pages.
- `check_no_secrets.py` — roda no CI e falha se `NTFY_TOPIC` ou
  `PORCUPINE_ACCESS_KEY` voltarem a ter valor no `config.py`
  versionado, ou se um `settings.json`/`device.json` for commitado. Lê
  o `config.py` como TEXTO (ast), não importando ele — senão o valor
  real vindo do settings.json seria confundido com o que está escrito
  no arquivo.
- `docs/` — o app de iPhone (PWA) publicado no GitHub Pages.
  `index.html` é autocontido; guarda tópico/wake word/IA escolhida em
  `localStorage`; monta `"<wake> <ia> <texto> over"` numa string só,
  recebida pelo relay e entregue a `DictationSession.handle_complete()`
  (não `handle()` — ver a decisão de arquitetura sobre isso: o " over"
  aqui é só um marcador fixo de "isto é tudo", não um convite pra
  vasculhar o meio do texto atrás dele). Envio automático com 3s de
  janela pra cancelar (transcrição erra; mandar errado é pior que um
  toque a mais). **O automático NÃO depende do Web Speech API** — ver
  a decisão de arquitetura sobre isso logo abaixo. Corpo de texto puro
  no POST de propósito — requisição simples, sem preflight CORS.
  **Limitação conhecida, não corrigida**: o campo "AI" da tela
  principal (`AIS`, ids `claude`/`chatgpt`/`perplexity`/`gemini`) é
  colado como TEXTO na mesma string, então ainda passa pelo roteador
  de texto livre do Mac — se o conteúdo ditado/digitado começar com a
  palavra "code"/"código" logo depois de escolher o chip "Claude", o
  roteador (ver `command_router.py` mais abaixo) enxerga "claude code"
  como o gatilho de duas palavras de `claude_code`, que o relay
  BLOQUEIA por segurança — a mensagem some sem chegar a nada, mesmo
  a pessoa tendo escolhido "Claude" sem ambiguidade nenhuma pelo toque.
  Corrigir direito exigiria o relay extrair o `ai_id` de um jeito que
  não dependa de re-adivinhar por texto livre o que o botão já sabia
  com certeza — mudança de contrato maior, não feita nesta leva
  (ver "Limitações conhecidas").
- `test_pwa.js` — 39 testes do PWA num Chromium DE VERDADE
  (Playwright), rodando no CI. **A peça mais validada do projeto** — a
  única testada em runtime real em vez de mocks. Achou dois defeitos
  visuais que nenhuma leitura de código teria pego: o `hidden` não
  esconde SVG (a regra do navegador só vale pro namespace HTML), e o
  `viewBox` do mascote incluía a moldura inteira.
- `.github/workflows/` — `tests.yml` (suíte Python + PWA + o guarda de
  segredos), `build-macos.yml` (o `.app`/`.dmg` num macOS real, com
  smoke test), `pages.yml` (publica o PWA).

Ferramentas de apoio:
- `doctor.py` — confere a config antes de rodar (dependências
  instaladas, dispositivo de entrada preferido detectável agora,
  tópico do ntfy não é óbvio/curto, Porcupine com as duas chaves ou
  nenhuma, `DEFAULT_AI` existe em `AI_TRIGGERS`). O check de
  dispositivo (`check_input_device()`) é só informativo — nunca conta
  como problema, porque não ter o mic ligado/pareado na hora de rodar
  `doctor.py` não é erro de config. Rodar `python3 doctor.py` antes de
  `python3 main.py`.
- `test_*.py` — 350 testes no total. Rodar com:
  `python3 -m unittest discover -p "test_*.py"`

iOS (`ios/SendToVisperIntent.swift`) — rascunho do App Intent que
publica no tópico ntfy quando disparado pela Siri/Atalhos/Botão de
Ação. **Nunca compilado, nunca aberto no Xcode** (ainda sem toolchain
Swift em nenhum ambiente Claude Code usado até agora — nem esta
sessão) — precisa criar um projeto Xcode novo, colar o arquivo
dentro, e validar do zero. Revisado com atenção mesmo sem poder
compilar: a lógica HTTP (POST sem `Content-Type`, corpo = texto puro,
sucesso = status 200) bate com a documentação pública do ntfy, mas
**tentei confirmar contra o ntfy.sh de verdade e não consegui — o
proxy de saída deste sandbox bloqueia ntfy.sh por política de egress
("connect_rejected" no proxy, não é limitação do código). Isso não é
específico desta sessão: nenhum ambiente Claude Code com esse tipo de
proxy vai conseguir validar isso — só dá pra confirmar rodando na
rede/Mac da Valeta mesmo.** Um achado concreto da revisão: nenhuma das
duas frases originais da Siri (`VisperShortcuts.appShortcuts`)
capturava o parâmetro `command` (faltava `\(\.$command)` embutido na
frase) — acrescentada uma terceira frase que captura explicitamente,
como caminho mais garantido; as três continuam sem testar de verdade
(precisa de Xcode). Ver comentários no topo do arquivo pro checklist
atualizado.

LaunchAgent (`launchd/com.valeta.visper.plist`) — inicia o vIsper
sozinho no login, sem Terminal aberto (ver "Deixar rodando sozinho"
no README pro passo a passo). Reinicia sozinho se crashar
(`KeepAlive`/`SuccessfulExit: false`), mas NÃO reabre depois de "Sair"
deliberado no menu — distinção que importa (`<true/>` sem o dict
reabriria sempre, inclusive depois de "Sair", o oposto do que faz
sentido). Assume um venv dedicado dentro da pasta do vIsper (agora
recomendado desde a Instalação no README, não só pro LaunchAgent) —
motivo: permissões do macOS (mic/Automação/Acessibilidade) são
concedidas por BINÁRIO específico, então usar o MESMO interpreter pra
teste manual e pro LaunchAgent evita ter que conceder tudo de novo.
**NUNCA TESTADO NUM MAC DE VERDADE** — o XML foi validado com
`plistlib` (Python, parser estrito — confirma que está bem formado e
que as chaves batem com o que eu pretendia), mas nenhum `launchctl`
de verdade carregou isso ainda; primeira coisa a conferir é se o
ícone aparece na barra de menu depois do login, e os logs
(`visper.out.log`/`visper.err.log`, na pasta do vIsper) se não
aparecer.

Empacotamento (`setup.py` + `build_mac_app.sh`) — transforma o código
Python num `vIsper.app` de duplo clique e monta um `vIsper.dmg` em
volta. Motivo de existir: a Valeta pediu explicitamente "um dmg e um
app pra instalar", depois de tropeçar justamente no atrito de
`cd` + `source venv/bin/activate` + `pip install` (ver "Preferências":
mínimo de atrito é critério de arquitetura aqui). Decisões tomadas:
- **py2app, não PyInstaller** — py2app é o que gera bundle `.app`
  nativo de barra de menu com `Info.plist` de verdade, que é
  exatamente do que o rumps precisa.
- **`LSUIElement = True`** — sem isso o app apareceria no Dock e no
  Cmd+Tab; é um app de barra de menu, não deve.
- **`NSMicrophoneUsageDescription` e `NSAppleEventsUsageDescription`
  são obrigatórias, não opcionais** — rodando por Terminal quem pedia
  permissão era o Terminal; num `.app` é o próprio app, e sem essas
  chaves o macOS moderno MATA o processo em vez de mostrar o diálogo.
  Texto delas em inglês de propósito (aparece na UI do sistema).
- **`argv_emulation` PRECISA ser False** — depende do Carbon, que não
  existe mais em 64-bit; travaria o app na abertura.
- **Assinatura ad-hoc (`codesign -s -`), não conta paga da Apple** —
  US$99/ano contraria o custo zero. O ad-hoc não tira o aviso do
  Gatekeeper (primeira abertura ainda precisa de botão direito →
  Abrir), mas dá ao app uma identidade ESTÁVEL, e isso importa porque
  o macOS amarra permissão concedida (mic/Acessibilidade) à
  assinatura — sem ele, toda recompilação pediria tudo de novo.
- **Dois modos de build**: standalone (padrão, autocontido, centenas
  de MB por causa do ctranslate2/onnxruntime que o faster-whisper
  puxa) e `--dev` (alias, segundos, mas o `.app` vira atalho pro venv
  desta pasta e quebra se ela sair do lugar). O `--dev` é o plano B
  documentado caso o standalone brigue com as libs nativas.
- **Ícone gerado no build, não versionado** — `sips`+`iconutil` fazem
  o `.icns` a partir de `design/mascot_concept_v1_preview.png` (400px,
  então 512/1024 são upscale e ficam macios — aceito porque o mascote
  ainda é conceito não aprovado). Trocar a arte é trocar o PNG.
**NUNCA RODOU NUM MAC** — só validação de sintaxe (`bash -n`,
`py_compile`). É a peça menos validada junto com o LaunchAgent.

iOS via app Atalhos (`ios/ATALHO_IPHONE.md`) — receita passo a passo
pra montar no app Atalhos (que já vem no iPhone) o mesmo POST no
tópico ntfy que o rascunho Swift faria. **Passou a ser o caminho
recomendado, e o Swift virou "avançado"**: iOS não instala app de
arquivo (não existe DMG de iPhone) — ou App Store, ou Xcode + conta;
com conta grátis o app EXPIRA EM 7 DIAS, com conta paga são US$99/ano.
As duas alternativas contrariam custo zero/mínimo atrito, e o Atalho
não custa nada, não expira, e já roda na Siri/Botão de Ação/Apple
Watch de graça (o Watch era uma das "ideias ainda não construídas" —
sai junto sem trabalho extra). Detalhe da receita que importa: o
Atalho monta `vIsper <ditado> over` numa string só, então ela cai
exatamente no caminho "abre e fecha no MESMO trecho" de
`dictation.py` — o que aquele bug de uma-respiração-só corrigiu é o
que faz o iPhone funcionar em um disparo. Não testado (sem iPhone
aqui).

Design (`design/`):
- `mascot_concept_v1.svg` — mascote colorido (lavanda), com preview
  em PNG. Conceito: "antena de som" no lugar de orelha de bicho,
  ancorado na função do produto (voz/escuta) em vez de um animal
  aleatório.
- `menubar_icon_template.svg` — versão monocromática/silhueta, pro
  ícone real da barra de menu do Mac (convenção da Apple: glifo
  simples, não arte colorida, pra funcionar em modo claro/escuro).
- `layouts_mockup.html` — mockup animado dos dois layouts (painel da
  barra de menu + app do iPhone), com a paleta de status completa (7
  cores, ver acima) e texto de produto em inglês. Tem prefers-
  reduced-motion respeitado.
- `DESIGN.md` — notas de paleta/estilo. **Desatualizado**: ainda não
  reflete a paleta de status expandida (só documentação, não afeta
  funcionamento).

Nenhum dos conceitos de design foi reagido pela Valeta ainda — pode
mudar bastante antes de virar assets de produção.

## Limitações conhecidas

1. Sem UI de configuração — tudo se ajusta editando `config.py`
   direto.
2. Tópico do ntfy é hardcoded no rascunho do Swift
   (`TROQUE_AQUI_PELO_MESMO_TOPICO_DO_MAC`) — precisa de um jeito
   melhor (tela de config no app, ou Keychain) antes de distribuir de
   verdade.
3. `_listen_loop_porcupine` em `main.py` nunca rodou numa máquina
   real — é a parte menos validada do projeto inteiro.
4. `audio_file_input.py` existe mas não está plugado em `main.py`.
5. Submenu dinâmico do rumps (`MenuItem.clear()`/`.add()`, `.state`,
   `.title`) nunca rodou contra o AppKit de verdade — a API foi
   conferida contra o source do pacote (não só documentação/memória),
   mas isso não substitui ver o menu abrir na barra de verdade. O
   mesmo vale pra `afplay` (earcon) e pra ler/escrever
   `~/Library/Application Support/vIsper/device.json` (persistência de
   escolha manual) — a LÓGICA tem teste (mockando `subprocess.Popen`/
   apontando pra um diretório temporário), mas nenhum dos dois tocou
   um Mac de verdade ainda.
6. Se DOIS dispositivos de entrada tiverem o MESMO nome (raro, mas
   possível), o submenu "Escolher microfone" mostra os dois com rótulo
   desambiguado por índice (`audio_input.label_devices()`) — mas
   seleção/persistência continuam pelo NOME puro (não o rótulo), então
   nesse caso raro escolher "um dos dois" e escolher "o outro" ainda
   resolvem pro mesmo nome salvo. Distinguir os dois de verdade
   exigiria persistir mais que o nome — não vale a complexidade pra um
   cenário tão raro.
7. `launchd/com.valeta.visper.plist` (início automático no login)
   nunca foi carregado por um `launchctl` de verdade — só validado
   como XML bem formado (`plistlib`). Ver "Próximos passos" #2.
8. O app empacotado não é assinado por conta paga da Apple, então a
   PRIMEIRA abertura exige botão direito → Abrir (Gatekeeper). Não
   tem como remover isso sem os US$99/ano.
9. **Ligar o GitHub Pages é um clique manual** (Settings → Pages →
   Source: GitHub Actions). O token do CI não tem permissão de
   administrador do repositório, então `configure-pages` com
   `enablement: true` falha com "Resource not accessible by
   integration" — confirmado numa execução real. O `pages.yml`
   degrada com instrução em vez de ficar vermelho pra sempre.
9b. **Depois de ligado, o Pages só publica de verdade quando o push é
   em `main` — pushes na branch de trabalho (`claude/**`, que o
   trigger do `pages.yml` alega suportar) falham em ~2s, ANTES de
   qualquer step rodar.** Achado revisando o histórico de execuções
   depois que a Valeta relatou "o app do telefone quase não
   funcionou": o site publicado (`mpvaleta.github.io/vIsper/`) ficou
   dias parado na versão da última vez que uma PR tinha sido mergeada
   em `main`, enquanto 3 pushes seguidos na branch de trabalho —
   incluindo o commit que trocou o envio automático do PWA de "só
   funciona com Web Speech API" pra "funciona por ociosidade, sem
   depender do Web Speech" — falharam ao publicar. A Valeta chegou a
   tentar `workflow_dispatch` manual na mesma branch e bateu no mesmo
   erro. O padrão (falha quase instantânea, zero steps executados) é a
   assinatura de uma regra de proteção de branch no ambiente de
   deployment `github-pages` do próprio repositório (Settings →
   Environments → github-pages → Deployment branches and tags) — algo
   que só a dona do repositório consegue ver/mudar, e que nenhuma
   ferramenta disponível nas sessões deste projeto consegue ler ou
   ajustar (não é um arquivo versionado). Efeito prático: **testar o
   app de iPhone pelo link publicado só reflete código que já foi
   mergeado em `main`** — testar antes disso exige servir `docs/`
   localmente (`python3 -m http.server` na pasta) ou aceitar que o
   teste real só vale depois do merge. Resolvido nesta sessão mergeando
   a PR pendente na hora (ver "O que JÁ foi validado" abaixo), mas a
   causa raiz (a regra de proteção) continua lá pra próxima branch de
   trabalho — vale checar aquele menu de Settings antes de assumir que
   "quase nada funciona" é bug de código.
10. `vad_filter=True` e `hotwords` foram acrescentados só no loop do
   Whisper contínuo (`main._listen_loop_whisper`).
   `porcupine_session.py` e `audio_file_input.py` continuam sem os
   dois — neles o áudio já vem recortado por outra coisa (detecção
   acústica / arquivo escolhido a dedo), então alucinação de silêncio
   é bem menos provável e a prioridade de vocabulário importa menos
   (o Porcupine já detectou a wake word pelo SOM); e mexer neles
   quebraria os dublês de modelo dos testes, que fixam a assinatura
   `transcribe(audio, language=None)`.
11. **"vIsper, cancela" não funciona no modo Porcupine.** Lá a wake
   word FECHA o ditado no instante em que o Porcupine a reconhece
   acusticamente — a palavra "cancela" vem depois disso e nunca chega
   a ser capturada, então o ditado já foi mandado. É inerente a fechar
   por detecção acústica, não um descuido: o modo Whisper contínuo (o
   padrão) transcreve o trecho inteiro antes de decidir, e é por isso
   que só nele dá pra distinguir "fecha" de "cancela".
12. Chunks de 4s sem sobreposição (`audio_input.AudioStream.chunks()`):
   uma palavra cortada exatamente na fronteira entre dois chunks pode
   não casar com nenhum gatilho. Conhecido, não corrigido — a correção
   (janela deslizante) muda o contrato de todo mundo que consome
   `chunks()`.
13. **Escolher o chip "Claude" no app de iPhone e ditar/digitar
   conteúdo que começa com "code"/"código" faz a mensagem ser
   BLOQUEADA em vez de aberta.** Achado numa auditoria de bugs depois
   que a Valeta relatou "quase nada funcionou" no telefone. Causa:
   `config.AI_TRIGGERS` tem `"claude": ["claude"]` e
   `"claude_code": ["claude code", "claude código"]` — quando o texto
   que sobra depois da wake word é "claude code review needed...", o
   roteador (`command_router._decide()`, ver a regra de desempate por
   COMPRIMENTO em "Decisões de arquitetura") prefere corretamente o
   gatilho de duas palavras "claude code" ao de uma palavra "claude",
   porque é exatamente essa regra que resolve o caso de VOZ
   equivalente ("vIsper claude code também abre um terminal" tem que
   abrir o Claude Code, não o Claude). O problema é que o app de
   iPhone já sabia com CERTEZA qual IA a pessoa queria (ela tocou no
   chip "Claude"), mas codifica essa certeza como texto livre
   ambíguo — jogando fora a própria vantagem de não depender de voz.
   `claude_code` está em `RELAY_BLOCKED_AIS` (abrir o Terminal
   remotamente é execução de comando — ver a decisão de segurança
   sobre isso), então o resultado prático é a mensagem inteira
   BLOQUEADA e descartada, com o telefone mostrando "Sent to your Mac"
   mesmo assim (o POST pro ntfy teve sucesso). **Não corrigido nesta
   leva**: a correção de verdade exige o relay extrair o `ai_id` de um
   jeito que não dependa de re-adivinhar por texto livre o que o botão
   já sabia com certeza (ex.: um contrato novo entre
   `relay_listener.py` e `dictation.py` que aceite o nome da IA já
   resolvido) — mudança de forma maior que as desta sessão, feitas com
   cuidado pra não arriscar regredir a regra de desempate que existe
   por um motivo real do lado da voz. Afeta só a combinação específica
   "chip Claude" + conteúdo começando em "code"/"código"; as outras
   três IAs não têm gatilho colidente nenhum.
14. **O rascunho Swift (`ios/SendToVisperIntent.swift`) e a receita do
   app Atalhos (`ios/ATALHO_IPHONE.md`) só abrem alguma coisa se o que
   for falado/ditado COMEÇAR com o nome de uma IA configurada** —
   documentado e corrigido nesta sessão (o Swift agora gruda a wake
   word e "over" em `perform()`; o Atalho já grudava, mas faltava
   avisar). Causa: os dois sempre grudam um "over" fixo no FIM da
   mensagem, então o roteador nunca vê "só a wake word sozinha" (que é
   o único caso que abre `DEFAULT_AI` sem precisar de nome de IA
   nenhum — ver `command_router._decide()`) — sem um nome reconhecido
   logo depois da wake word, a mensagem chega no Mac e não abre NADA,
   sem erro visível em lugar nenhum. O Swift nunca foi compilado (sem
   Xcode em nenhuma sessão até agora), então esse fix está só revisado
   por leitura, não testado — ver o cabeçalho do arquivo pro checklist
   completo antes de considerar pronto.

### O que JÁ foi validado em máquina real (não é mais suposição)

Atualizar esta lista sempre que algo sair do "nunca testado":

- **O `.app`/`.dmg` compila e ABRE num macOS de verdade.** O job
  `build-macos.yml` (runner macos-14, Apple Silicon) passou incluindo o
  smoke test que abre o bundle e confere que ele sobrevive 20s — que é
  exatamente a falha silenciosa do py2app quando falta lib nativa.
  Então: a lista `PACKAGES`, o `user_settings` no bundle, e a cópia do
  libportaudio estão corretos. O que continua não validado é o
  comportamento COM microfone e COM permissões concedidas.
- **O app de iPhone funciona num navegador real** (39 testes,
  `test_pwa.js`, no CI a cada push).
- **O link publicado (`mpvaleta.github.io/vIsper/`) está atualizado
  com o código mais recente** — confirmado nesta sessão via a API do
  GitHub (histórico de execuções do `pages.yml` + `git diff` entre
  `main` e a branch de trabalho): a PR pendente com o fix de envio
  automático sem Web Speech API estava, até aqui, mergeada localmente
  mas NUNCA publicada (ver limitação 9b). Mergeada e republicada nesta
  sessão; a execução em `main` terminou verde. Antes disso, qualquer
  teste no iPhone real estava rodando a versão de semanas atrás.
- **`python3 main.py` roda de verdade num Mac** — a Valeta testou.
  Ícone aparece, escuta liga, permissões de Microfone/Acessibilidade
  funcionam, o modelo baixa e carrega. Achou (e já está corrigido) o
  crash real de thread documentado em "Decisões de arquitetura"
  (`AppHelper.callAfter`) e o bug do `mic_menu.clear()` (ver histórico
  de commits) — os dois só apareceram rodando de verdade, nenhum dos
  dois foi pego só lendo código. O que continua sem validação completa
  de ponta a ponta: uma sessão inteira sem crash (abrir → ditar →
  mandar, repetido), e o Porcupine com hardware real.

## Próximos passos, em ordem de prioridade

1. Rodar e testar o app do Mac de verdade (permissões de microfone e
   de Acessibilidade — ver README) — nada abaixo importa se essa base
   não estiver validada primeiro. Testar os dois caminhos de escuta
   (Whisper contínuo é o padrão; Porcupine só ativa com as duas
   chaves configuradas), e os dois dispositivos de entrada (DJI Mic e
   o Sony XM5 da Valeta) — auto-detecção E escolha manual pelo
   submenu. Prestar atenção especial ao aviso de qualidade Bluetooth
   (ver README) — confirmar que aparece e que o áudio do sistema
   realmente degrada como esperado, já que isso nunca foi ouvido de
   verdade, só deduzido de como o Bluetooth clássico funciona. Testar
   também: os earcons tocando nos momentos certos (abrir/mandar/
   cancelar — os três sons são diferentes de propósito), e a
   persistência de escolha manual sobrevivendo a um `python3 main.py`
   novo (escolher o Sony, fechar o app, abrir de novo, conferir que já
   veio marcado sem precisar escolher de novo). O que mudou desde o
   último teste dela e precisa de olhar específico:
   - **falar português E inglês** na mesma sessão, conferindo o
     `[pt]`/`[en]` no "Heard:" — e se aparecer `[en→pt]`, isso é a
     correção funcionando, não um erro;
   - **os ícones**: são a silhueta do mascote agora, e o azul de
     "mandou" tem que voltar pro verde sozinho em ~2s;
   - **"vIsper, cancela"**: descarta o ditado, som DIFERENTE do de
     mandar, e nada é colado;
   - **os ajustes pelo menu** ("Wake word…", "Spoken languages…") —
     conferir principalmente que trocar o idioma vale na hora, sem
     reabrir o app;
   - **no iPhone**: ditar pela tecla de microfone do TECLADO (não pelo
     botão do app) e não encostar em mais nada — tem que mandar
     sozinho depois de uns segundos.
   - **"Recent activity…"** é o que usar quando algo NÃO funcionar:
     em vez de tentar de novo e torcer, abrir ali e comparar as duas
     colunas — se o `heard` mostrar a frase certa mas não houver `→`
     nenhum, o problema é o casamento do gatilho; se o `heard` já vier
     torto, é transcrição (ou idioma); se não houver linha nenhuma, o
     áudio não está chegando. Vale mandar print disso junto de
     qualquer relato de bug — é o que faltou da última vez.
2. Depois do item 1 validado manualmente por uns dias: configurar o
   LaunchAgent (`launchd/com.valeta.visper.plist`, ver README) —
   confirmar que o ícone aparece sozinho no login, que "Sair" não
   reabre sozinho, e que crashar de verdade (força bruta: `kill -9`
   no processo) reabre.
3. Testar `relay_listener.py` contra o ntfy.sh real (`curl -d "vIsper
   claude teste" https://ntfy.sh/SEU_TOPICO` e confirmar que chega) —
   só dá pra fazer no Mac/rede da Valeta mesmo, sandboxes de Claude
   Code com proxy de saída restrito (como o usado nas últimas rodadas
   deste projeto) não conseguem alcançar ntfy.sh pra validar isso.
4. Se for usar Porcupine: conseguir AccessKey + arquivo `.ppn`
   (console.picovoice.ai) e testar `_listen_loop_porcupine` com mic
   de verdade.
5. Plugar `audio_file_input.py` em `main.py` (menu ou pasta
   vigiada).
6. Abrir `ios/SendToVisperIntent.swift` num projeto Xcode novo, fazer
   compilar, testar o Atalho de ponta a ponta — prestar atenção
   especial em qual das três frases da Siri realmente pede/preenche o
   parâmetro `command` direito (ver comentário no arquivo).
7. Design: reagir aos conceitos em `design/` — manter, ajustar ou
   trocar de direção — e só então gerar o resto dos assets (ícone em
   todos os tamanhos exigidos pelo iOS/macOS).

## Ideias sugeridas, ainda não construídas

A Valeta decide o que vale a pena construir — isso é só uma lista de
ideias que surgiram, não um compromisso:
- Envio automático depois de alguns segundos de silêncio NO MAC,
  como rede de segurança pra quando esquecer de repetir a wake word.
  **Já existe no iPhone** (o PWA arma `IDLE_MS` a cada digitação e
  cai na mesma janela de cancelamento), mas no Mac é bem mais
  arriscado: lá o microfone fica aberto o tempo todo, então "parou de
  falar" acontece o tempo todo sem querer dizer "terminei". Precisaria
  ser opt-in e provavelmente com janela de cancelamento maior.
- Comando que manda direto o que já está copiado (pula o ditado).
- Apple Watch: o mesmo App Intent do iPhone, disparável pelo relógio
  — combina com o caso de uso do treino.

## Preferências da Valeta pra esse projeto

- **Testar duas vezes antes de considerar pronto** — rodando de
  verdade sempre que possível, não só checando sintaxe. Quando
  hardware real não está disponível, testar a lógica isolada com
  mocks e deixar bem claro, por escrito, o que ficou sem validar.
- **Zero custo adicional e o mínimo de atrito possível** são
  prioridade em qualquer decisão de arquitetura — é o critério de
  desempate padrão quando há mais de um jeito de resolver algo.
- Comunica em português e inglês.
- Texto de produto (UI) em inglês; código/documentação deste projeto
  em português.

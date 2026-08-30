# Direção visual — vIsper

Baseado na referência que a Valeta mandou: personagens-cubo fofos
(estilo voxel/toy, cantos arredondados, não pixel duro/8-bit), chão
espelhado refletindo o personagem, fundo verde-água.

## Paleta
- Fundo: gradiente vertical `#9FDCC0` → `#5FAE8F` (mint → verde-água)
- Corpo do mascote: gradiente `#CCC0F4` → `#A48FE6` (lavanda) — cor
  nova, não repete nenhum dos 3 personagens da referência (rosa,
  branco, preto)
- Destaque "top do cubo": `#E4DCFA` a 60% de opacidade
- Bochecha: `#F4A9A0` a 70%
- Onda sonora (elemento de destaque, no lugar do coração/sparkle da
  referência): `#4FC7B8`

## Mascote v1 (`mascot_concept_v1.svg`)
Conceito: uma "antena de som" no lugar de orelha de bicho — já que o
vIsper não tem um bicho definido, ancorei o design na própria função
(escutar/sussurrar) em vez de escolher um animal aleatório. Onda
sonora ao lado faz o papel que o coração faz na coelha e o sparkle
faz no gato da referência: o "estado emocional" do personagem.

Primeiro rascunho, não iterado — reação da Valeta decide se isso vira
a direção final ou se muda personagem/paleta.

## Um ponto técnico importante pra quando isso virar ícone de verdade
O mascote colorido serve bem pra: ícone do app no iPhone, tela de
"sobre", site/marketing. **Não serve direto** pro ícone da barra de
menu do Mac — esse, por convenção da Apple (e pra funcionar em modo
claro/escuro), costuma ser um glifo simples monocromático (silhueta),
não arte colorida. Já criei uma primeira versão simplificada só pra
isso: `menubar_icon_template.svg` (+ preview em PNG) — tirei os
detalhes de rosto (não sobrevivem no tamanho minúsculo da barra de
menu) e mantive só a silhueta + a onda sonora, preto sólido, pronto
pra usar como "template image" do macOS (o sistema inverte a cor
sozinho conforme o modo claro/escuro).

## App de iPhone — como ficou de verdade

`iphone_app_claro.png` / `iphone_app_escuro.png` são capturas REAIS do
app (`docs/index.html`) rodando num Chromium com viewport de iPhone 13
— não mockup. É a primeira peça do projeto com aparência validada em
vez de imaginada.

Traduz a paleta de status pra tela: o ponto ao lado de "Ready" muda de
cor conforme o estado (cinza ocioso, coral ditando, âmbar mandando,
azul enviado, terracota offline), e as cores de MARCA (lavanda) ficam
só no logo, nos chips de IA e no botão — a separação que o CLAUDE.md
exige.

Dois defeitos que só apareceram na captura, e que nenhuma leitura de
código pegaria:
- O anel de contagem do envio automático ficava desenhado por cima do
  botão o tempo todo. O atributo `hidden` NÃO esconde elemento SVG — a
  regra `[hidden] { display: none }` do navegador vale só pro namespace
  HTML. Precisou de uma regra CSS explícita.
- O mascote no badge do cabeçalho estava minúsculo e jogado num canto:
  o `viewBox` era o `0 0 400 400` do arquivo original, com muita
  moldura vazia em volta do desenho. Recortado pro conteúdo real
  (`130 114 185 185`).

## Barra de menu do Mac

O ícone do app É o estado (`main.STATUS_ICONS`, os PNGs de
`status_icons/`, gerados por `design/generate_status_icons.py`).
**Forma e cor comunicam coisas diferentes, de propósito**: a forma é a
silhueta do mascote — a MESMA de `menubar_icon_template.svg`, o
briefing — e não muda nunca, porque é o que identifica o vIsper na
barra; a cor é a paleta semântica, e é ela que diz o estado (cinza
parado, âmbar carregando, verde escutando, coral ditando, azul mandou,
terracota erro). É a regra de "cor de marca separada de cor de status"
do CLAUDE.md aplicada num eixo a mais.

Passou por três versões, e as duas primeiras ensinaram uma coisa cada:

1. **Emoji** (⏳🎙🟢🔴🔵🟠) como texto do título. Funcionava, mas a
   Valeta testou e apontou que "as cores que você falou não estão
   funcionando" — emoji usa as cores do FONTE da Apple, não a paleta
   documentada (🟠 não é terracota; 🎙 não tem cor de estado nenhuma).
2. **Círculo colorido sólido.** Cor certa, forma jogada fora — "os
   ícones deveriam seguir o briefing inicial". Lição: acertar um eixo
   não vale quebrar o outro.
3. **Silhueta do mascote na cor do estado** (atual). Os dois eixos ao
   mesmo tempo.

Por que NÃO usar "template image" (a convenção da Apple de silhueta
monocromática invertida pelo sistema): template é uma cor só, por
definição — ligar isso apagaria a cor do estado pelo mesmo motivo do
emoji, só que por outro caminho. Confirmado no source do rumps 0.4.0
(`_nsimage_from_file`, `image.setTemplate_`).

Detalhe técnico de quem for mexer no gerador: o rumps fixa a imagem em
20×20 PONTOS (`image.setSize_((20, 20))`, sem como passar outro valor
pela propriedade `.icon`), então o PNG precisa ser QUADRADO — imagem
não-quadrada seria espremida. Os 88px de lado dão bitmap de sobra pra
reduzir com qualidade em tela Retina 2x (40px) e 3x (60px).

`test_status_icons.py` fecha os dois círculos comparando os BYTES do
PNG: a cor contra o hex de `layouts_mockup.html`, e pontos do desenho
(dentro do corpo, na haste da antena, no vão ENTRE as antenas) contra
a geometria de `menubar_icon_template.svg`.

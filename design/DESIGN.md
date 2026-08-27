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

O ícone do app É o estado, com a mesma paleta semântica (ver
`main.STATE_GLYPHS`): ⏳ carregando, 🎙 parado, 🟢 escutando,
🔴 ditando, 🔵 mandou, 🟠 erro.

Círculo colorido em vez do glifo monocromático de
`menubar_icon_template.svg` por um motivo prático: a convenção da
Apple (silhueta template, invertida pelo sistema) é boa pra IDENTIDADE,
mas não consegue comunicar ESTADO — template image é uma cor só, por
definição. Trocar o desenho a cada estado exigiria seis assets e não
resolveria o mais importante, que é dar pra distinguir de relance
"escutando" de "parado". O glifo continua valendo pra quando o app
tiver um ícone fixo de identidade.

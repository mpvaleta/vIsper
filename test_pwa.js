/*
 * Teste de ponta a ponta do app de iPhone (docs/index.html) num
 * Chromium de verdade, emulando um iPhone.
 *
 * O que dá pra validar aqui: a montagem da mensagem que vai pro Mac
 * (que é o contrato com dictation.py), a leitura do link de
 * configuração, a persistência, o seletor de IA, e o envio automático
 * por ociosidade com a janela de cancelamento — inclusive o caminho
 * SEM Web Speech (digitar/ditar pelo teclado), que é o que precisa
 * funcionar sem apertar nada. A requisição pro ntfy.sh é interceptada
 * — o proxy deste sandbox bloqueia ntfy.sh de qualquer forma.
 *
 * O que NÃO dá pra validar aqui e continua só testável num iPhone de
 * verdade: o Safari do iOS, o "Adicionar à Tela de Início", o
 * armazenamento separado do app standalone, e o Web Speech API.
 */
const { chromium, devices } = require('playwright');
const http = require('http');
const fs = require('fs');
const path = require('path');

const RAIZ = path.join(__dirname, 'docs');
const PORTA = 8099;
const TIPOS = {
  '.html': 'text/html',
  '.png': 'image/png',
  '.webmanifest': 'application/manifest+json',
};

let falhas = 0;
let passou = 0;

function check(nome, condicao, detalhe) {
  if (condicao) {
    passou++;
    console.log(`  ok   ${nome}`);
  } else {
    falhas++;
    console.log(`  FALHA ${nome}${detalhe ? ' — ' + detalhe : ''}`);
  }
}

const servidor = http.createServer((req, res) => {
  const rel = decodeURIComponent(req.url.split('?')[0].split('#')[0]);
  const arquivo = path.join(RAIZ, rel === '/' ? 'index.html' : rel);
  if (!arquivo.startsWith(RAIZ) || !fs.existsSync(arquivo)) {
    res.writeHead(404); res.end('nao encontrado'); return;
  }
  res.writeHead(200, { 'Content-Type': TIPOS[path.extname(arquivo)] || 'text/plain' });
  res.end(fs.readFileSync(arquivo));
});

(async () => {
  await new Promise((r) => servidor.listen(PORTA, r));
  const navegador = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined,
  });

  const TOPICO = 'visper-TesteAbc123XyZ';
  const base = `http://localhost:${PORTA}/`;

  async function novaPagina(contexto) {
    const pagina = await contexto.newPage();
    // Intercepta o POST pro ntfy e guarda o corpo, em vez de sair na rede.
    contexto.enviados = [];
    await pagina.route('**/ntfy.sh/**', (rota) => {
      contexto.enviados.push({
        url: rota.request().url(),
        metodo: rota.request().method(),
        corpo: rota.request().postData(),
      });
      rota.fulfill({ status: 200, body: 'ok' });
    });
    return pagina;
  }

  // ---------------------------------------------------------------
  console.log('\n1) Link de configuração do setup_visper.py');
  let ctx = await navegador.newContext(devices['iPhone 13']);
  let pagina = await novaPagina(ctx);
  await pagina.goto(`${base}#t=${TOPICO}&w=V%C3%A9sper`);
  await pagina.waitForTimeout(300);

  const guardado = await pagina.evaluate(() =>
    JSON.parse(localStorage.getItem('visper.settings.v1') || '{}'));
  check('tópico lido do fragmento', guardado.topic === TOPICO, JSON.stringify(guardado));
  check('wake word acentuada decodificada', guardado.wake === 'Vésper', guardado.wake);
  check('vai direto pra tela principal',
    await pagina.locator('#screen-main').getAttribute('data-active') === 'true');
  check('mostra o aviso de adicionar à tela de início',
    await pagina.locator('#install-tip').isVisible());
  check('hash preservado fora do modo standalone (é o que leva o tópico pro atalho)',
    (await pagina.evaluate(() => location.hash)).includes(TOPICO));

  // ---------------------------------------------------------------
  console.log('\n2) Mensagem montada pro Mac (contrato com dictation.py)');
  await pagina.fill('#text', 'qual é a previsão do tempo');
  await pagina.click('#btn-send');
  await pagina.waitForTimeout(400);

  check('fez exatamente um POST', ctx.enviados.length === 1, `${ctx.enviados.length}`);
  const env = ctx.enviados[0] || {};
  check('POST no tópico certo', (env.url || '').endsWith(TOPICO), env.url);
  check('método POST', env.metodo === 'POST', env.metodo);
  check('mensagem = wake + ia + conteúdo + over',
    env.corpo === 'Vésper claude qual é a previsão do tempo over', env.corpo);
  check('campo limpo depois de mandar',
    (await pagina.inputValue('#text')) === '');

  // ---------------------------------------------------------------
  console.log('\n3) Seletor de IA');
  ctx.enviados.length = 0;
  await pagina.locator('.ai-chip', { hasText: 'Perplexity' }).click();
  await pagina.fill('#text', 'quem ganhou ontem');
  await pagina.click('#btn-send');
  await pagina.waitForTimeout(400);
  check('usa a IA escolhida',
    (ctx.enviados[0] || {}).corpo === 'Vésper perplexity quem ganhou ontem over',
    (ctx.enviados[0] || {}).corpo);

  const escolhida = await pagina.evaluate(() =>
    JSON.parse(localStorage.getItem('visper.settings.v1')).ai);
  check('escolha de IA persiste', escolhida === 'perplexity', escolhida);

  // ---------------------------------------------------------------
  console.log('\n4) Erro de rede aparece em vez de sumir');
  ctx.enviados.length = 0;
  await pagina.unroute('**/ntfy.sh/**');
  await pagina.route('**/ntfy.sh/**', (rota) => rota.fulfill({ status: 500, body: 'erro' }));
  await pagina.fill('#text', 'isto vai falhar');
  await pagina.click('#btn-send');
  await pagina.waitForTimeout(500);
  check('status vira offline', await pagina.locator('#status').getAttribute('data-state') === 'offline');
  check('toast de erro visível', await pagina.locator('#toast').isVisible());
  check('texto NÃO é perdido quando o envio falha',
    (await pagina.inputValue('#text')) === 'isto vai falhar');

  // ---------------------------------------------------------------
  console.log('\n5) Tela de configuração');
  await pagina.click('#btn-settings');
  await pagina.waitForTimeout(200);
  check('abre a configuração',
    await pagina.locator('#screen-setup').getAttribute('data-active') === 'true');
  check('tópico atual pré-preenchido',
    (await pagina.inputValue('#in-topic')) === TOPICO);

  await pagina.fill('#in-topic', 'https://ntfy.sh/visper-ColadoDaUrl/');
  await pagina.click('#btn-save');
  await pagina.waitForTimeout(200);
  const limpo = await pagina.evaluate(() =>
    JSON.parse(localStorage.getItem('visper.settings.v1')).topic);
  check('URL inteira colada vira só o tópico', limpo === 'visper-ColadoDaUrl', limpo);

  // ---------------------------------------------------------------
  console.log('\n6) Primeira abertura, sem link');
  const ctx2 = await navegador.newContext(devices['iPhone 13']);
  const p2 = await novaPagina(ctx2);
  await p2.goto(base);
  await p2.waitForTimeout(300);
  check('cai na configuração quando não há tópico',
    await p2.locator('#screen-setup').getAttribute('data-active') === 'true');

  await p2.click('#btn-save');
  await p2.waitForTimeout(200);
  check('salvar vazio não sai da configuração',
    await p2.locator('#screen-setup').getAttribute('data-active') === 'true');

  // ---------------------------------------------------------------
  console.log('\n7) Acessibilidade e tema escuro');
  const ctx3 = await navegador.newContext({
    ...devices['iPhone 13'], colorScheme: 'dark',
  });
  const p3 = await novaPagina(ctx3);
  await p3.goto(`${base}#t=${TOPICO}`);
  await p3.waitForTimeout(300);
  const corFundo = await p3.evaluate(() =>
    getComputedStyle(document.body).backgroundColor);
  check('tema escuro pinta o fundo', !corFundo.includes('246, 244, 251'), corFundo);

  const tamanhoFonte = await p3.evaluate(() =>
    getComputedStyle(document.getElementById('text')).fontSize);
  check('campo com 16px (abaixo disso o iOS dá zoom sozinho)',
    parseFloat(tamanhoFonte) >= 16, tamanhoFonte);

  const alvo = await p3.evaluate(() => {
    const r = document.getElementById('btn-send').getBoundingClientRect();
    return Math.min(r.width, r.height);
  });
  check('botão principal com alvo de toque >= 44px', alvo >= 44, `${alvo}px`);

  const rolagem = await p3.evaluate(() =>
    document.documentElement.scrollWidth <= window.innerWidth + 1);
  check('sem rolagem horizontal', rolagem);

  // ---------------------------------------------------------------
  console.log('\n8) Erros de console');
  const erros = [];
  const p4 = await novaPagina(await navegador.newContext(devices['iPhone 13']));
  p4.on('pageerror', (e) => erros.push(e.message));
  p4.on('console', (m) => { if (m.type() === 'error') erros.push(m.text()); });
  await p4.goto(`${base}#t=${TOPICO}`);
  await p4.waitForTimeout(400);
  await p4.fill('#text', 'oi');
  await p4.click('#btn-send');
  await p4.waitForTimeout(400);
  check('nenhum erro de JS', erros.length === 0, erros.join(' | '));

  // ---------------------------------------------------------------
  // O pedido era literal: "eu nao quero ter que apertar enviar para o
  // Mac". O Web Speech API nao existe no Chromium sem cabecalho, e no
  // iPhone real ele some quando o app roda a partir da tela de inicio
  // — entao o caminho que PRECISA funcionar sem toque nenhum e o do
  // teclado (tecla de microfone) e o de digitar: parou de mexer,
  // manda sozinho.
  console.log('\n9) Envio automatico sem tocar em "Send to Mac"');
  const ctx5 = await navegador.newContext(devices['iPhone 13']);
  const p5 = await novaPagina(ctx5);
  await p5.goto(`${base}#t=${TOPICO}&w=V%C3%A9sper`);
  await p5.waitForTimeout(300);

  // Digitar (é o mesmo evento `input` que a tecla de microfone do
  // teclado do iPhone dispara) e nao encostar em mais nada.
  await p5.type('#text', 'que horas sao');
  await p5.waitForTimeout(3000);   // 2.5s de ociosidade + folga
  check('parar de escrever comeca a contagem sozinho',
    (await p5.locator('#send-label').textContent()) === 'Tap to cancel',
    await p5.locator('#send-label').textContent());
  check('anel de contagem aparece',
    await p5.locator('#ring-path').isVisible());

  await p5.waitForTimeout(3400);   // deixa a contagem terminar
  check('mandou sem nenhum toque no botao', ctx5.enviados.length === 1,
    `${ctx5.enviados.length}`);
  check('mensagem automatica no mesmo formato do envio manual',
    (ctx5.enviados[0] || {}).corpo === 'Vésper claude que horas sao over',
    (ctx5.enviados[0] || {}).corpo);

  // Continuar escrevendo durante a contagem cancela e rearma — quem
  // esta corrigindo nao pode ver a frase pela metade sair voando.
  ctx5.enviados.length = 0;
  await p5.type('#text', 'primeira parte');
  await p5.waitForTimeout(3000);
  check('contagem em andamento antes de corrigir',
    (await p5.locator('#send-label').textContent()) === 'Tap to cancel');
  await p5.type('#text', ' e a segunda');
  await p5.waitForTimeout(200);
  check('digitar no meio da contagem cancela',
    (await p5.locator('#send-label').textContent()) === 'Send to Mac',
    await p5.locator('#send-label').textContent());
  // `hidden` em SVG so responde a atributo, nao a propriedade — se
  // alguem trocar de volta pra `.hidden = true`, o anel fica desenhado
  // por cima do botao pra sempre e este check pega.
  check('anel some quando a contagem e cancelada',
    await p5.locator('#ring-path').isHidden());
  check('nada foi mandado pela metade', ctx5.enviados.length === 0);

  await p5.waitForTimeout(6200);   // ociosidade + contagem de novo
  check('parar de corrigir volta a mandar sozinho', ctx5.enviados.length === 1,
    `${ctx5.enviados.length}`);
  check('mandou a frase inteira, nao so o pedaco',
    (ctx5.enviados[0] || {}).corpo ===
      'Vésper claude primeira parte e a segunda over',
    (ctx5.enviados[0] || {}).corpo);

  // Cancelar de proposito tem que valer: se a ociosidade rearmasse
  // sozinha, o toque de cancelar nao serviria pra nada.
  ctx5.enviados.length = 0;
  await p5.type('#text', 'isso eu nao quero mandar');
  await p5.waitForTimeout(3000);
  await p5.click('#btn-send');
  await p5.waitForTimeout(200);
  check('toque no botao durante a contagem cancela',
    (await p5.locator('#send-label').textContent()) === 'Send to Mac');
  await p5.waitForTimeout(6200);
  check('cancelado de proposito continua cancelado',
    ctx5.enviados.length === 0, `${ctx5.enviados.length}`);

  // Desligar o automatico desliga de verdade.
  await p5.click('#btn-settings');
  await p5.waitForTimeout(200);
  await p5.uncheck('#in-autosend');
  await p5.click('#btn-save');
  await p5.waitForTimeout(200);
  ctx5.enviados.length = 0;
  await p5.fill('#text', '');
  await p5.type('#text', 'sem automatico agora');
  await p5.waitForTimeout(6200);
  check('com o automatico desligado nao manda nada sozinho',
    ctx5.enviados.length === 0, `${ctx5.enviados.length}`);
  check('e o botao continua mandando na mao',
    await (async () => {
      await p5.click('#btn-send');
      await p5.waitForTimeout(400);
      return ctx5.enviados.length === 1;
    })(), `${ctx5.enviados.length}`);

  await navegador.close();
  servidor.close();

  console.log(`\n${passou} ok, ${falhas} falha(s)`);
  process.exit(falhas ? 1 : 0);
})();

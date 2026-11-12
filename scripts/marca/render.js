// uso: node render.js entrada.svg saida.png largura altura [escala] [fundo]
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const [inp, out, w, h, esc, fundo] = process.argv.slice(2);
  const svg = fs.readFileSync(inp, 'utf8');
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: +w, height: +h }, deviceScaleFactor: +(esc || 1) });
  await p.setContent(`<html><body style="margin:0;background:${fundo || 'transparent'}">` +
    svg.replace(/width="[\d.]+" height="[\d.]+"/, `width="${w}" height="${h}"`) + '</body></html>');
  await p.screenshot({ path: out, omitBackground: !fundo, clip: { x: 0, y: 0, width: +w, height: +h } });
  await b.close();
})();

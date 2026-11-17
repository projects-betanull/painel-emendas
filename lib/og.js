// Cartão de prévia (Open Graph) em PNG 1200x630, desenhado sem dependências: glifos pré-rasterizados
// (lib/og_fonte.js) + PNG montado aqui, comprimido com o CompressionStream nativo do Workers/Node.
import { ESTILOS, ALFA_GZ } from "./og_fonte.js";

export const LARGURA = 1200, ALTURA = 630;
const COR = { fundo: [0xfb, 0xfb, 0xf9], tinta: [0x1c, 0x1f, 0x24], suave: [0x5d, 0x64, 0x70], acento: [0x0b, 0x6e, 0x4f], linha: [0xe3, 0xe5, 0xe8] };
const MARGEM = 80, UTIL = LARGURA - 2 * MARGEM;

async function lerTudo(stream) {
  const partes = [];
  const leitor = stream.getReader();
  for (;;) {
    const { done, value } = await leitor.read();
    if (done) break;
    partes.push(value);
  }
  const total = partes.reduce((s, p) => s + p.length, 0);
  const out = new Uint8Array(total);
  let i = 0;
  for (const p of partes) { out.set(p, i); i += p.length; }
  return out;
}

async function transformar(bytes, stream) {
  const w = stream.writable.getWriter();
  w.write(bytes); w.close();
  return lerTudo(stream.readable);
}

let alfa = null; // glifos descomprimidos uma vez por isolate
async function carregarAlfa() {
  if (!alfa) {
    const bin = Uint8Array.from(atob(ALFA_GZ), (c) => c.charCodeAt(0));
    alfa = await transformar(bin, new DecompressionStream("gzip"));
  }
  return alfa;
}

function glifo(est, ch) {
  const g = est.g[ch];
  if (g) return g;
  const sem = ch.normalize("NFD").replace(/[̀-ͯ]/g, "");
  return est.g[sem] || null;
}

export function medir(estilo, texto) {
  const est = ESTILOS[estilo];
  let x = 0;
  for (const ch of texto) { const g = glifo(est, ch); if (g) x += g[4]; }
  return x;
}

// Corta o texto com reticências para caber na largura.
export function caber(estilo, texto, largura = UTIL) {
  if (medir(estilo, texto) <= largura) return texto;
  let t = texto;
  while (t.length > 1 && medir(estilo, t + "…") > largura) t = t.slice(0, -1);
  return t.trimEnd() + "…";
}

// PNG indexado (1 byte por pixel): fundo + 63 níveis de cada cor sobre o fundo. Texto nunca se sobrepõe,
// então misturar sempre com o fundo basta; deixa a imagem 3x menor antes da compressão (menos CPU).
const CORES = ["tinta", "suave", "acento", "linha"];
const NIVEIS = 63;
const PALETA = (() => {
  const p = new Uint8Array(3 * (1 + CORES.length * NIVEIS));
  p.set(COR.fundo, 0);
  CORES.forEach((nome, ci) => {
    for (let n = 1; n <= NIVEIS; n++) {
      const k = n / NIVEIS, o = 3 * (1 + ci * NIVEIS + n - 1);
      for (let c = 0; c < 3; c++) p[o + c] = Math.round(COR.fundo[c] + (COR[nome][c] - COR.fundo[c]) * k);
    }
  });
  return p;
})();
const indice = (nome, nivel) => 1 + CORES.indexOf(nome) * NIVEIS + nivel - 1;
const LINHA = LARGURA + 1; // byte de filtro + pixels

function escrever(px, estilo, texto, x, base, cor) {
  const est = ESTILOS[estilo], ini0 = indice(cor, 1) - 1;
  for (const ch of texto) {
    const g = glifo(est, ch);
    if (!g) continue;
    const [w, h, dx, dy, av, ini] = g;
    const gx = Math.round(x + dx), gy = base + dy;
    for (let j = 0; j < h; j++) {
      const y = gy + j;
      if (y < 0 || y >= ALTURA) continue;
      let o = y * LINHA + 1 + gx, a = ini + j * w;
      for (let i = 0; i < w; i++, o++, a++) {
        const v = alfa[a];
        if (v < 3 || gx + i < 0 || gx + i >= LARGURA) continue;
        px[o] = ini0 + Math.max(1, Math.round((v * NIVEIS) / 255));
      }
    }
    x += av;
  }
  return x;
}

function retangulo(px, x0, y0, x1, y1, cor) {
  const c = indice(cor, NIVEIS);
  for (let y = y0; y < y1; y++) px.fill(c, y * LINHA + 1 + x0, y * LINHA + 1 + x1);
}

const CRC = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; }
  return t;
})();
function crc32(bytes) {
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) c = CRC[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
function bloco(tipo, dados) {
  const out = new Uint8Array(12 + dados.length);
  const v = new DataView(out.buffer);
  v.setUint32(0, dados.length);
  out.set([...tipo].map((c) => c.charCodeAt(0)), 4);
  out.set(dados, 8);
  v.setUint32(8 + dados.length, crc32(out.subarray(4, 8 + dados.length)));
  return out;
}

async function png(px) {
  const ihdr = new Uint8Array(13);
  const v = new DataView(ihdr.buffer);
  v.setUint32(0, LARGURA); v.setUint32(4, ALTURA); ihdr.set([8, 3, 0, 0, 0], 8); // 8 bits, paleta
  const idat = await transformar(px, new CompressionStream("deflate"));
  const partes = [new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10]), bloco("IHDR", ihdr), bloco("PLTE", PALETA), bloco("IDAT", idat), bloco("IEND", new Uint8Array())];
  const out = new Uint8Array(partes.reduce((s, p) => s + p.length, 0));
  let i = 0;
  for (const p of partes) { out.set(p, i); i += p.length; }
  return out;
}

// dados: { titulo, sub, valor, linha1, linha2, rodape } (textos prontos, gerados pelo ETL).
export async function desenharCartao(dados) {
  await carregarAlfa();
  const px = new Uint8Array(LINHA * ALTURA); // tudo zero: filtro 0 em cada linha e cor de fundo
  retangulo(px, 0, 0, 24, ALTURA, "acento");

  const x = escrever(px, "corpo", "Emendas", MARGEM, 96, "tinta");
  escrever(px, "corpo", ".", x, 96, "acento");
  escrever(px, "rodape", "para onde vai o dinheiro das emendas parlamentares", x + 24, 96, "suave");

  const titulo = dados.titulo || "";
  const estT = medir("titulo", titulo) <= UTIL ? "titulo" : "titulo2";
  escrever(px, estT, caber(estT, titulo), MARGEM, 208, "tinta");
  if (dados.sub) escrever(px, "corpo", caber("corpo", dados.sub), MARGEM, 266, "suave");
  if (dados.valor) escrever(px, "valor", caber("valor", dados.valor), MARGEM - 6, 412, "acento");
  if (dados.linha1) escrever(px, "corpo", caber("corpo", dados.linha1), MARGEM, 470, "tinta");
  if (dados.linha2) escrever(px, "corpo", caber("corpo", dados.linha2), MARGEM, 522, "tinta");
  retangulo(px, MARGEM, 556, LARGURA - MARGEM, 558, "linha");
  escrever(px, "rodape", caber("rodape", dados.rodape || "Fonte: Portal da Transparência (CGU) · valores reproduzidos como publicados"), MARGEM, 600, "suave");
  return png(px);
}

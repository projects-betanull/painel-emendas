// Ficha de uma organização: lê ../d/<3 primeiros dígitos do CNPJ>.json e monta a página.
(function () {
  const main = document.getElementById("ficha");
  const c = (new URLSearchParams(location.search).get("c") || "").replace(/\D/g, "").slice(0, 8).padStart(8, "0");
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
  const brl = (v) => "R$ " + Number(v || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const num = (v, moeda) => Number(v || 0).toLocaleString("pt-BR", { maximumFractionDigits: 0 }) + " " + esc(moeda || "");
  const tabela = (cab, linhas, nums = []) => '<div class="tabela"><table><thead><tr>' +
    cab.map((h, i) => '<th class="' + (nums.includes(i) ? "n" : "") + '">' + esc(h) + "</th>").join("") + "</tr></thead><tbody>" +
    linhas.map((l) => "<tr>" + l.map((v, i) => '<td class="' + (nums.includes(i) ? "n" : "") + '">' + v + "</td>").join("") + "</tr>").join("") +
    "</tbody></table></div>";

  if (c === "00000000") { main.innerHTML = '<p>Informe o CNPJ. <a href="../">Buscar uma ONG</a>.</p>'; return; }
  fetch("../d/" + c.slice(0, 3) + ".json").then((r) => r.ok ? r.json() : {}).then((lote) => {
    const f = lote[c];
    if (!f) { main.innerHTML = "<h1>Organização não encontrada</h1><p>O CNPJ " + esc(c) + ' não está no cadastro de OSCs ativas do IPEA. <a href="../">Buscar uma ONG</a>.</p>'; return; }
    document.title = f.nome + " · Transparência das ONGs";
    const partes = [];
    partes.push('<p class="migalha"><a href="../../">Início</a> › <a href="../">ONGs</a> › ' + esc(f.uf) + "</p>");
    partes.push("<h1>" + esc(f.nome) + "</h1>");
    if (f.fantasia && f.fantasia !== f.nome) partes.push('<p class="sub">' + esc(f.fantasia) + "</p>");
    const alertas = [];
    if (f.cepim) alertas.push('<i class="selo alerta">Impedida de receber recursos federais (CEPIM)</i>');
    if (f.estrangeira) alertas.push('<i class="selo">Organização estrangeira' + (f.estrangeira !== "exterior" ? " · " + esc(f.estrangeira) : "") + "</i>");
    if (f.situacao && f.situacao.toLowerCase() !== "ativa") alertas.push('<i class="selo">Situação na Receita: ' + esc(f.situacao) + "</i>");
    if (alertas.length) partes.push('<p class="selos">' + alertas.join(" ") + "</p>");

    const mun = f.ibge ? esc(f.municipio) + " (" + esc(f.uf) + ")" : esc(f.municipio) + " (" + esc(f.uf) + ")";
    partes.push("<dl>" + [
      ["CNPJ", esc(f.cnpj)], ["Natureza jurídica", esc(f.natureza)], ["Sede", mun], ["Fundação", esc(f.fundacao ? f.fundacao.split("-").reverse().join("/") : "não informada")],
      ["Área de atuação", esc(f.areas || "não informada")],
      ["Estabelecimentos", f.estabelecimentos + (f.ufs && f.ufs.length > 1 ? " em " + f.ufs.length + " estados (" + f.ufs.map(esc).join(", ") + ")" : "")],
    ].map(([k, v]) => "<dt>" + k + "</dt><dd>" + v + "</dd>").join("") + "</dl>");

    const ki = [];
    if (f.emendas) ki.push(["Emendas parlamentares recebidas", brl(f.emendas.total)]);
    if (f.convenios) ki.push(["Convênios federais: valor liberado", brl(f.convenios.liberado)]);
    if (f.internacional) ki.push(["Projetos de doadores estrangeiros", String(new Set(f.internacional.map((l) => l[7])).size)]);
    if (ki.length) partes.push('<section class="kpis">' + ki.map(([k, v]) => '<div class="kpi"><strong>' + v + "</strong><span>" + k + "</span></div>").join("") + "</section>");
    else partes.push("<p>Não encontramos emendas, convênios federais nem projetos de doadores estrangeiros ligados a este CNPJ nas fontes consultadas.</p>");

    if (f.emendas) {
      const e = f.emendas;
      const anos = Object.entries(e.por_ano).sort();
      const links = e.explorar.map(([uf, rot]) => '<a href="../../explorar/#' + esc(new URLSearchParams({ l: "autor", c: "ano", "f.uf": uf, "f.favorecido": rot.join("|") }).toString()) + '">Ver no Explorar (' + esc(uf) + ") ›</a>").join(" ");
      partes.push("<section><h2>Emendas parlamentares</h2>" +
        tabela(["Ano", "Valor recebido"], anos.map(([a, v]) => [esc(a), brl(v)]), [1]) +
        "<h3>Quem enviou</h3>" + tabela(["Autor da emenda", "Valor"], e.autores.map(([n, v]) => [esc(n), brl(v)]), [1]) +
        '<p class="dica">' + links + '</p><p class="aviso-ligacao">Fonte: arquivo de favorecidos de emendas do Portal da Transparência, pelo CNPJ.</p></section>');
    }
    if (f.convenios) {
      const v = f.convenios;
      partes.push("<section><h2>Convênios e parcerias com o governo federal</h2><p>" + v.n + " instrumento(s), valor total " + brl(v.valor) +
        ", liberado " + brl(v.liberado) + ".</p>" +
        tabela(["Órgão", "Liberado"], v.por_orgao.map(([o, x]) => [esc(o), brl(x)]), [1]) +
        "<h3>Maiores instrumentos</h3>" +
        tabela(["Nº", "Ano", "Tipo", "Concedente", "Objeto", "Local", "Situação", "Valor", "Liberado"],
          v.lista.map((l) => ['<a href="https://portaldatransparencia.gov.br/convenios/' + encodeURIComponent(l[0]) + '">' + esc(l[0]) + "</a>", esc(l[1]), esc(l[2]), esc(l[3]), esc(l[4]), esc(l[5]) + "/" + esc(l[6]), esc(l[7]), brl(l[8]), brl(l[9])]), [7, 8]) +
        (v.municipios.length ? "<p><strong>Onde executou convênios:</strong> " + v.municipios.map(esc).join(", ") + "</p>" : "") +
        '<p class="aviso-ligacao">Fonte: Portal da Transparência (CGU), convênios pelo CNPJ do convenente. Parte das emendas é paga por convênio; não some os dois valores.</p></section>');
    }
    if (f.internacional) {
      partes.push("<section><h2>Financiamento internacional declarado</h2>" +
        "<p>Projetos com destino ao Brasil em que o doador cita esta organização. Valores na moeda declarada pelo doador (zero quando ele não informa quanto repassou a ela).</p>" +
        tabela(["Doador", "Projeto", "Anos", "Papel", "Valor declarado", "Ligação"],
          f.internacional.map((l) => [esc(l[0]), '<a href="https://d-portal.org/ctrack.html#view=act&aid=' + encodeURIComponent(l[7]) + '">' + esc(l[1]) + "</a>",
            esc(l[2]) + (l[3] && l[3] !== l[2] ? "–" + esc(l[3]) : ""), esc(l[4]), l[5] ? num(l[5], l[6]) : "—",
            esc(l[9]) + (l[9] && l[9].startsWith("nome") ? " (" + esc(l[8]) + ")" : "")]), [4]) +
        '<p class="aviso-ligacao">Fonte: dados publicados pelos próprios doadores no padrão IATI (d-portal). Quando o doador não informa o CNPJ, a ligação é feita pelo nome idêntico ao do cadastro e pode haver erro: confira no link do projeto.</p></section>');
    }
    if (f.cepim) {
      partes.push("<section><h2>Impedimento (CEPIM)</h2>" + tabela(["Convênio", "Órgão", "Motivo"], f.cepim.map((l) => l.map(esc))) +
        '<p class="aviso-ligacao">Fonte: Cadastro de Entidades Privadas sem Fins Lucrativos Impedidas (CGU), como publicado.</p></section>');
    }
    partes.push('<p class="dica"><a href="../#' + esc(new URLSearchParams({ uf: f.uf, q: f.municipio }).toString()) + '">Outras ONGs em ' + esc(f.municipio) + " ›</a></p>");
    main.innerHTML = partes.join("\n");
  }).catch(() => { main.innerHTML = "<p>Não foi possível carregar os dados agora. Tente de novo em instantes.</p>"; });
})();

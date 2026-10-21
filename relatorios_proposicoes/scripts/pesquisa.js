/* Pesquisa facetada sobre a base local de proposições.
   Cada faceta conta os itens que passam por todos os outros filtros, de modo que as listas
   só oferecem opções compatíveis com o que já foi escolhido. O tipo da proposição usa um
   autocompletar sobre a lista oficial de tipos; a seleção só filtra depois de confirmada. */
(function () {
  "use strict";

  var D = JSON.parse(document.getElementById("pq-dados").textContent);
  var form = document.getElementById("pq-filtros");
  var campoTipo = document.getElementById("pq-tipo");
  var listaTipos = document.getElementById("pq-tp-lista");
  var painelTipos = form.querySelector("[data-autocompletar]");

  var FORA = ["Arquivada", "Transformado em Norma Jurídica", "Retirado pelo(a) Autor(a)", "Vetado totalmente", "Transformado em nova proposição", "Perdeu a eficácia"];
  var LIMITE = 20;
  var API = "https://dadosabertos.camara.leg.br/api/v2/proposicoes";
  var FICHA = "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=";
  var ETAPAS = [
    ["Ficha e situação", "GET /proposicoes/{id} — ementa, regime, apreciação, status"],
    ["Tramitações", "GET /proposicoes/{id}/tramitacoes — histórico com documentos"],
    ["Autoria", "GET /proposicoes/{id}/autores e /deputados — foto, partido, UF"],
    ["Relatoria e pareceres", "Relator, prazos, PRL/PAR/SBT e versão válida"],
    ["Temas e indexação", "GET /proposicoes/{id}/temas e keywords"],
    ["Apensados e documentos", "GET /proposicoes/{id}/relacionadas — árvore e anexos"],
    ["Análise estratégica", "Riscos, oportunidades e plano de ação com fontes oficiais"],
    ["Publicação", "Gera o relatório Detalhes de Proposições Legislativas"]
  ];
  var ROTULOS = { q: "Assunto", numero: "Número", ano: "Ano", partido: "Partido", uf: "UF", autor: "Autor", tema: "Tema", situ: "Situação", orgao: "Órgão", regime: "Regime", aprec: "Apreciação", de: "De", ate: "Até" };

  function norm(x) {
    return String(x || "").toLocaleLowerCase("pt-BR").normalize("NFD").replace(/[̀-ͯ]/g, "");
  }
  function fmt(iso) {
    return iso ? iso.slice(8, 10) + "/" + iso.slice(5, 7) + "/" + iso.slice(0, 4) : "—";
  }

  /* ---------- Itens e tabelas ---------- */
  var itens = D.L.map(function (l) {
    var si = D.S[l[7]];
    return {
      id: l[0], tp: l[1], nu: l[2], an: l[3], dt: l[4], em: l[5], si: si, og: D.O[l[8]], ap: D.AP[l[9]], rg: D.RG[l[10]], ul: l[11],
      aut: l[13].map(function (i) { return D.A[i]; }), na: l[14], te: l[15].map(function (i) { return D.T[i]; }),
      txt: norm(l[5] + " " + l[6]), tram: FORA.indexOf(si) < 0 ? "sim" : "nao"
    };
  });
  var tipos = D.TP.map(function (t) {
    return { v: t[0], nome: t[1], chave: norm(t[0]), nomes: [t[1]].concat(t[2]).map(function (n) { return [n, norm(n)]; }) };
  });
  var nomeTipo = {};
  tipos.forEach(function (t) { nomeTipo[t.v] = t.nome; });
  var autorRot = {};
  itens.forEach(function (x) {
    x.aut.forEach(function (a) { autorRot[a[0]] = a[1] ? a[0] + " (" + a[1] + "-" + a[2] + ")" : a[0]; });
  });

  /* ---------- Estado ---------- */
  function inicial() {
    return { q: "", tp: [], numero: "", ano: "", partido: "", uf: "", autor: "", tema: "", situ: "", orgao: "", regime: "", aprec: "", tram: "todas", de: "", ate: "" };
  }
  function acInicial() {
    return { txt: "", pend: [], aberto: false, ativo: 0 };
  }
  var st = { f: inicial(), filtroAutor: "", limite: LIMITE, ordem: "recentes", ac: acInicial(), det: 0, copiado: 0 };

  function definir(patch) {
    st.f = Object.assign({}, st.f, patch);
    st.limite = LIMITE;
    renderizar();
  }

  /* ---------- Filtros ---------- */
  var testes = {
    q: function (x, f) { return norm(f.q).split(/\s+/).filter(Boolean).every(function (t) { return x.txt.indexOf(t) >= 0; }); },
    tp: function (x, f) { return !f.tp.length || f.tp.indexOf(x.tp) >= 0; },
    numero: function (x, f) { return !f.numero || String(x.nu) === f.numero.trim(); },
    ano: function (x, f) { return !f.ano || String(x.an) === f.ano.trim(); },
    partido: function (x, f) { return !f.partido || x.aut.some(function (a) { return a[1] === f.partido; }); },
    uf: function (x, f) { return !f.uf || x.aut.some(function (a) { return a[2] === f.uf; }); },
    autor: function (x, f) { return !f.autor || x.aut.some(function (a) { return a[0] === f.autor; }); },
    tema: function (x, f) { return !f.tema || x.te.indexOf(f.tema) >= 0; },
    situ: function (x, f) { return !f.situ || x.si === f.situ; },
    orgao: function (x, f) { return !f.orgao || x.og === f.orgao; },
    regime: function (x, f) { return !f.regime || x.rg === f.regime; },
    aprec: function (x, f) { return !f.aprec || x.ap === f.aprec; },
    tram: function (x, f) { return f.tram === "todas" || x.tram === f.tram; },
    de: function (x, f) { return !f.de || x.dt >= f.de; },
    ate: function (x, f) { return !f.ate || x.dt <= f.ate; }
  };
  var chaves = Object.keys(testes);
  function passa(x, exceto) {
    return chaves.every(function (k) { return k === exceto || testes[k](x, st.f); });
  }

  /* Contagem de uma faceta com todos os filtros, menos o dela. */
  function faceta(chave, valoresDe) {
    var base = itens.filter(function (x) { return passa(x, chave); });
    var cont = {};
    base.forEach(function (x) {
      Array.from(new Set(valoresDe(x))).forEach(function (v) { if (v) cont[v] = (cont[v] || 0) + 1; });
    });
    return { base: base.length, cont: cont };
  }

  function opcoes(chave, valoresDe, op) {
    op = op || {};
    var fc = faceta(chave, valoresDe), cont = fc.cont, atual = st.f[chave];
    var vals = Object.keys(cont);
    if (atual && vals.indexOf(atual) < 0) vals.push(atual);
    vals.sort(op.ordem || function (a, b) { return (cont[b] || 0) - (cont[a] || 0) || a.localeCompare(b, "pt-BR"); });
    var filtro = op.filtro ? norm(op.filtro) : "";
    if (filtro) vals = vals.filter(function (v) { return norm(v).indexOf(filtro) >= 0 || v === atual; });
    var lista = [{ v: "", t: op.todos || "Todos", n: fc.base, on: !atual, dis: false }];
    vals.forEach(function (v) {
      var n = cont[v] || 0, on = atual === v;
      lista.push({ v: v, t: op.rot ? op.rot(v) : v, n: n, on: on, dis: !n && !on });
    });
    return lista;
  }

  /* ---------- Montagem de elementos ---------- */
  function h(tag, attrs, filhos) {
    var el = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v === false || v === null || v === undefined) return;
      if (k === "texto") el.textContent = v;
      else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), v);
      else if (v === true) el.setAttribute(k, "");
      else el.setAttribute(k, v);
    });
    (filhos || []).forEach(function (f) {
      if (f !== null && f !== undefined && f !== false) el.appendChild(typeof f === "string" ? document.createTextNode(f) : f);
    });
    return el;
  }
  function svg(caminhos, tamanho, largura) {
    var NS = "http://www.w3.org/2000/svg";
    var el = document.createElementNS(NS, "svg");
    [["aria-hidden", "true"], ["width", tamanho], ["height", tamanho], ["viewBox", "0 0 24 24"], ["fill", "none"], ["stroke", "currentColor"], ["stroke-width", largura || "1.8"], ["stroke-linecap", "round"], ["stroke-linejoin", "round"]].forEach(function (a) { el.setAttribute(a[0], a[1]); });
    caminhos.forEach(function (d) {
      var p = document.createElementNS(NS, "path");
      p.setAttribute("d", d);
      el.appendChild(p);
    });
    return el;
  }
  function iconeRemover() { return svg(["M6 6l12 12", "M18 6L6 18"], 14); }
  function trocar(alvo, filhos) {
    alvo.replaceChildren.apply(alvo, filhos);
  }
  function saida(nome, texto) {
    form.parentNode.querySelectorAll('[data-saida="' + nome + '"]').forEach(function (el) { el.textContent = texto; });
  }

  /* Mantém o foco no rádio marcado quando a lista é reconstruída. */
  function preservandoFoco(fn) {
    var ativo = document.activeElement;
    var nome = ativo && ativo.type === "radio" ? ativo.name : null;
    fn();
    if (nome) {
      var marcado = form.querySelector('input[type="radio"][name="' + nome + '"]:checked');
      if (marcado) marcado.focus();
    }
  }

  function listaRadios(chave, lista) {
    var alvo = form.querySelector('[data-faceta="' + chave + '"]');
    trocar(alvo, lista.map(function (o) {
      return h("label", { class: "opcao" + (o.on ? " opcao--marcada" : "") + (o.dis ? " opcao--inativa" : "") }, [
        h("input", { type: "radio", name: chave, value: o.v, checked: o.on, disabled: o.dis, onchange: function () { definir(chave === "tram" ? { tram: o.v } : objeto(chave, o.v)); } }),
        h("span", { class: "opcao__texto", texto: o.t }),
        h("span", { class: "opcao__total", texto: String(o.n) })
      ]);
    }));
  }
  function objeto(k, v) {
    var o = {};
    o[k] = v;
    return o;
  }

  /* ---------- Autocompletar de tipos ---------- */
  function sugestoesTipos(cont) {
    var ac = st.ac, termo = norm(ac.txt.trim()), sug;
    if (!termo) {
      sug = tipos.filter(function (t) { return cont[t.v] || ac.pend.indexOf(t.v) >= 0 || st.f.tp.indexOf(t.v) >= 0; })
        .map(function (t) { return { t: t, sub: "", rank: -(cont[t.v] || 0) }; });
      sug.sort(function (a, b) { return a.rank - b.rank || a.t.v.localeCompare(b.t.v); });
      return sug;
    }
    sug = [];
    tipos.forEach(function (t) {
      var rank = t.chave === termo ? 0 : t.chave.indexOf(termo) === 0 ? 1 : 9, sub = "";
      t.nomes.forEach(function (par, i) {
        var pos = par[1].indexOf(termo);
        if (pos < 0) return;
        var r = (pos === 0 || par[1][pos - 1] === " " ? 2 : 3) + (i ? 0.5 : 0);
        if (r < rank) { rank = r; sub = i ? par[0] : ""; }
      });
      if (rank < 9) sug.push({ t: t, sub: sub, rank: rank });
    });
    sug.sort(function (a, b) {
      return a.rank - b.rank || (cont[b.t.v] || 0) - (cont[a.t.v] || 0) || a.t.nome.length - b.t.nome.length || a.t.v.localeCompare(b.t.v);
    });
    return sug.slice(0, 40);
  }

  var sugAtuais = [];
  function alternarTipo(v) {
    var p = st.ac.pend;
    st.ac.pend = p.indexOf(v) >= 0 ? p.filter(function (y) { return y !== v; }) : p.concat([v]);
    renderizar();
  }
  function abrirTipos() {
    if (st.ac.aberto) return;
    st.ac = { txt: st.ac.txt, pend: st.f.tp.slice(), aberto: true, ativo: 0 };
    renderizar();
  }
  function confirmarTipos(lista) {
    st.ac = acInicial();
    campoTipo.value = "";
    definir({ tp: lista });
  }
  function cancelarTipos() {
    st.ac = acInicial();
    campoTipo.value = "";
    renderizar();
  }

  function renderTipos(cont) {
    var ac = st.ac, termo = norm(ac.txt.trim());
    var sug = sugAtuais = ac.aberto ? sugestoesTipos(cont) : [];
    var ativo = Math.min(ac.ativo, Math.max(sug.length - 1, 0));
    st.ac.ativo = ativo;

    var conf = form.querySelector("[data-tipos-confirmados]");
    conf.hidden = !st.f.tp.length;
    trocar(conf, st.f.tp.map(function (v) {
      var nome = nomeTipo[v] || v;
      return h("button", { type: "button", class: "chip", title: nome, "aria-label": "Remover tipo " + v + " — " + nome,
        onclick: function () { definir({ tp: st.f.tp.filter(function (y) { return y !== v; }) }); } },
        [h("strong", { texto: v }), h("span", { class: "chip__total", texto: String(cont[v] || 0) }), iconeRemover()]);
    }));

    painelTipos.hidden = !ac.aberto;
    campoTipo.setAttribute("aria-expanded", ac.aberto ? "true" : "false");
    if (ac.aberto && sug.length) campoTipo.setAttribute("aria-activedescendant", "pq-tp-" + ativo);
    else campoTipo.removeAttribute("aria-activedescendant");
    if (!ac.aberto) return;

    saida("legendaTipos", termo ? sug.length + (sug.length === 1 ? " TIPO ENCONTRADO" : " TIPOS ENCONTRADOS") : "TIPOS PRESENTES NA BASE · DIGITE PARA VER OS " + D.TP.length);
    saida("rotuloConfirmar", "Confirmar seleção" + (ac.pend.length ? " (" + ac.pend.length + ")" : ""));
    var filhos = sug.map(function (o, i) {
      var v = o.t.v, on = ac.pend.indexOf(v) >= 0, n = cont[v] || 0;
      return h("label", { id: "pq-tp-" + i, class: "opcao" + (on ? " opcao--marcada" : "") + (i === ativo ? " opcao--ativa" : "") + (!n ? " opcao--zero" : ""),
        role: "option", "aria-selected": on ? "true" : "false", onmouseenter: function () { if (st.ac.ativo !== i) { st.ac.ativo = i; renderizar(); } } }, [
        h("input", { type: "checkbox", tabindex: "-1", value: v, checked: on, onchange: function () { alternarTipo(v); } }),
        h("span", { class: "opcao__texto" }, [h("strong", { texto: v }), " · " + o.t.nome, o.sub ? h("span", { class: "opcao__sub", texto: o.sub }) : null]),
        h("span", { class: "opcao__total", title: "Proposições na base com os demais filtros", texto: String(n) })
      ]);
    });
    if (!sug.length) filhos.push(h("span", { class: "lista-opcoes__vazia", texto: "Nenhum tipo corresponde a “" + ac.txt + "”." }));
    trocar(listaTipos, filhos);
  }

  campoTipo.addEventListener("focus", abrirTipos);
  campoTipo.addEventListener("input", function () {
    st.ac = { txt: campoTipo.value, aberto: true, ativo: 0, pend: st.ac.aberto ? st.ac.pend : st.f.tp.slice() };
    renderizar();
  });
  campoTipo.addEventListener("keydown", function (e) {
    var k = e.key, ac = st.ac, sug = sugAtuais, ativo = ac.ativo;
    if (k === "ArrowDown" || k === "ArrowUp") {
      e.preventDefault();
      if (!ac.aberto) { abrirTipos(); return; }
      st.ac.ativo = sug.length ? (ativo + (k === "ArrowDown" ? 1 : -1) + sug.length) % sug.length : 0;
      renderizar();
      var el = document.getElementById("pq-tp-" + st.ac.ativo);
      if (el && el.scrollIntoView) el.scrollIntoView({ block: "nearest" });
    } else if (k === " " && ac.aberto && sug[ativo] && (e.ctrlKey || !ac.txt)) {
      e.preventDefault();
      alternarTipo(sug[ativo].t.v);
    } else if (k === "Enter") {
      e.preventDefault();
      if (!ac.aberto) { abrirTipos(); return; }
      if (!ac.pend.length && sug[ativo]) { confirmarTipos([sug[ativo].t.v]); return; }
      confirmarTipos(ac.pend.slice());
    } else if (k === "Escape") {
      e.preventDefault();
      cancelarTipos();
    }
  });
  painelTipos.addEventListener("click", function (e) {
    var b = e.target.closest("[data-acao-tipo]");
    if (!b) return;
    var acao = b.dataset.acaoTipo;
    if (acao === "todos") {
      st.ac.pend = Array.from(new Set(st.ac.pend.concat(sugAtuais.map(function (o) { return o.t.v; }))));
      renderizar();
    } else if (acao === "limpar") {
      st.ac.pend = [];
      renderizar();
    } else if (acao === "confirmar") {
      confirmarTipos(st.ac.pend.slice());
    } else {
      cancelarTipos();
    }
  });

  /* ---------- Resultados ---------- */
  function corSituacao(s) {
    if (/Arquivada|Retirado|Vetado|eficácia/.test(s)) return " selo-situacao--fora";
    if (/Norma Jurídica/.test(s)) return " selo-situacao--norma";
    if (/Pronta para Pauta|Aguardando Parecer/.test(s)) return " selo-situacao--andamento";
    return "";
  }

  function solicitacao(x, sigla) {
    return "Gerar o relatório “Detalhes de Proposições Legislativas” para o " + sigla + " (idProposicao " + x.id + "): executar o pipeline completo na API de Dados Abertos da Câmara (ficha, tramitações com documentos, autoria, relatoria e pareceres, temas e indexação, apensados e documentos anexos), produzir a análise estratégica com fontes oficiais e gerar o relatório com data de emissão de hoje.";
  }

  function copiar(texto, area, id) {
    function ok() { st.copiado = id; renderizar(); }
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(texto).then(ok, ok); return; }
    } catch (err) { /* cai no modo manual */ }
    if (area) {
      area.focus();
      area.select();
      try { document.execCommand("copy"); } catch (err) { /* seleção manual */ }
    }
    ok();
  }

  function painelDetalhes(x, sigla) {
    var pronto = D.detalhes[String(x.id)];
    var fechar = function () { st.det = 0; st.copiado = 0; renderizar(); };
    var filhos = [
      h("div", { class: "detalhes__topo" }, [
        h("span", { class: "rotulo-mono rotulo-mono--tinta", texto: "PIPELINE_DE_DETALHES · ID " + x.id }),
        h("span", { class: "estado-detalhes rotulo-mono" + (pronto ? " estado-detalhes--ok" : ""), texto: pronto ? "DETALHES DISPONÍVEIS" : "DETALHES AINDA NÃO GERADOS" })
      ]),
      h("ol", { class: "etapas" }, ETAPAS.map(function (e, i) {
        return h("li", { class: "etapa" + (pronto ? " etapa--ok" : "") }, [
          h("span", { class: "etapa__numero", texto: String(i + 1) }),
          h("span", {}, [h("strong", { texto: e[0] }), h("span", { class: "opcao__sub", texto: e[1].replace("{id}", x.id) })])
        ]);
      }))
    ];
    var acoes = [];
    if (pronto) {
      filhos.push(h("p", { class: "detalhes__texto" }, ["Os dados desta proposição já alimentam o relatório ", h("strong", { texto: "Detalhes de Proposições Legislativas" }), " (“" + pronto.titulo + "”), com coleta em " + fmt(pronto.coleta) + "."]));
      acoes.push(h("a", { class: "botao botao--primario", href: pronto.arquivo, "aria-label": "Abrir o relatório de detalhes de " + sigla, texto: "Abrir relatório de detalhes" }));
    } else {
      var texto = solicitacao(x, sigla);
      var area = h("textarea", { class: "campo campo--solicitacao", readonly: true, rows: "4", "aria-label": "Solicitação de geração para " + sigla, onfocus: function (e) { try { e.target.select(); } catch (err) { /* sem seleção */ } } });
      area.value = texto;
      filhos.push(h("div", { class: "detalhes__texto" }, [
        h("p", { texto: "Esta página não executa o pipeline sozinha (ela não acessa a internet). Copie a solicitação abaixo e envie ao Claude: ele coleta os dados atualizados, faz a análise e gera o relatório de detalhes." }),
        area
      ]));
      acoes.push(h("button", { type: "button", class: "botao botao--primario", onclick: function () { copiar(texto, area, x.id); }, texto: st.copiado === x.id ? "Solicitação copiada ✓" : "Copiar solicitação" }));
    }
    acoes.push(
      h("a", { class: "botao", href: FICHA + x.id, target: "_blank", rel: "noopener noreferrer", "aria-label": "Abrir ficha de tramitação de " + sigla + " em nova aba", texto: "Ficha na Câmara ↗" }),
      h("a", { class: "botao", href: API + "/" + x.id, target: "_blank", rel: "noopener noreferrer", "aria-label": "Abrir dados de " + sigla + " na API em nova aba", texto: "Dados na API ↗" }),
      h("button", { type: "button", class: "botao", onclick: fechar, texto: "Fechar" })
    );
    filhos.push(h("div", { class: "detalhes__acoes" }, acoes));
    return h("div", { id: "pq-det-" + x.id, class: "detalhes", role: "region", "aria-label": "Detalhes de " + sigla,
      onkeydown: function (e) { if (e.key === "Escape") fechar(); } }, filhos);
  }

  function cartao(x) {
    var sigla = x.tp + " " + x.nu + "/" + x.an, aberto = st.det === x.id;
    var autores = x.aut.length ? x.aut.slice(0, 2).map(function (a) { return autorRot[a[0]] || a[0]; }).join(", ") + (x.na > 2 ? " e mais " + (x.na - 2) : "") : "—";
    return h("li", { class: "resultado" }, [
      h("div", { class: "resultado__topo" }, [
        h("button", { type: "button", class: "resultado__sigla", "aria-expanded": aberto ? "true" : "false", "aria-controls": "pq-det-" + x.id, title: "Gerar ou abrir os detalhes desta proposição",
          onclick: function () { st.det = aberto ? 0 : x.id; st.copiado = 0; renderizar(); } }, [sigla, svg(["M4 12h12", "M12 6l6 6-6 6"], 16)]),
        h("span", { class: "rotulo-mono", texto: "APRESENTADA EM " + fmt(x.dt) })
      ]),
      h("p", { class: "resultado__ementa", title: x.em, texto: x.em }),
      h("div", { class: "resultado__autor" }, [h("strong", { texto: "Autor:" }), " " + autores]),
      h("div", { class: "resultado__selos" }, [
        h("span", { class: "rotulo-mono selo-situacao" + corSituacao(x.si), texto: x.si.toUpperCase() }),
        h("span", { class: "rotulo-mono selo-orgao", texto: "ÓRGÃO " + x.og }),
        h("span", { class: "rotulo-mono selo-regime", texto: x.rg.replace(/ \(.*\)$/, "").toUpperCase() })
      ]),
      h("div", { class: "resultado__rodape", texto: "Temas: " + x.te.join(", ") + " · Última movimentação " + fmt(x.ul) }),
      aberto ? painelDetalhes(x, sigla) : null
    ]);
  }

  function urlApi() {
    var f = st.f, ps = [];
    f.tp.forEach(function (t) { ps.push("siglaTipo=" + t); });
    if (f.numero) ps.push("numero=" + encodeURIComponent(f.numero.trim()));
    if (f.ano) ps.push("ano=" + encodeURIComponent(f.ano.trim()));
    if (f.autor) ps.push("autor=" + encodeURIComponent(f.autor));
    if (f.partido) ps.push("siglaPartidoAutor=" + encodeURIComponent(f.partido));
    if (f.uf) ps.push("siglaUfAutor=" + encodeURIComponent(f.uf));
    if (f.tema) { var c = D.TC[D.T.indexOf(f.tema)]; if (c) ps.push("codTema=" + c); }
    if (f.q) ps.push("keywords=" + encodeURIComponent(f.q.trim()));
    if (f.de) ps.push("dataApresentacaoInicio=" + f.de);
    if (f.ate) ps.push("dataApresentacaoFim=" + f.ate);
    ps.push("ordem=DESC", "ordenarPor=id", "itens=100");
    return API + "?" + ps.join("&");
  }

  function chipsAtivos() {
    var f = st.f, chips = [];
    Object.keys(ROTULOS).forEach(function (k) {
      if (!f[k]) return;
      var valor = k === "de" || k === "ate" ? fmt(f[k]) : k === "autor" ? autorRot[f[k]] || f[k] : f[k];
      chips.push({ t: ROTULOS[k] + ": " + valor, tirar: function () { definir(objeto(k, "")); } });
    });
    f.tp.forEach(function (t) {
      chips.push({ t: "Tipo: " + t + " — " + (nomeTipo[t] || t), tirar: function () { definir({ tp: st.f.tp.filter(function (y) { return y !== t; }) }); } });
    });
    if (f.tram !== "todas") chips.push({ t: "Em tramitação: " + (f.tram === "sim" ? "Sim" : "Não"), tirar: function () { definir({ tram: "todas" }); } });
    return chips;
  }

  /* ---------- Renderização ---------- */
  function renderizar() {
    var f = st.f;
    var filtrados = itens.filter(function (x) { return passa(x, null); });
    var tpF = faceta("tp", function (x) { return [x.tp]; });

    preservandoFoco(function () {
      var tramF = faceta("tram", function (x) { return [x.tram]; });
      listaRadios("tram", [["todas", "Todas", tramF.base], ["sim", "Sim", tramF.cont.sim || 0], ["nao", "Não", tramF.cont.nao || 0]].map(function (o) {
        return { v: o[0], t: o[1], n: o[2], on: f.tram === o[0], dis: false };
      }));
      listaRadios("partido", opcoes("partido", function (x) { return x.aut.map(function (a) { return a[1]; }); }));
      listaRadios("uf", opcoes("uf", function (x) { return x.aut.map(function (a) { return a[2]; }); }, { ordem: function (a, b) { return a.localeCompare(b); } }));
      listaRadios("autor", opcoes("autor", function (x) { return x.aut.map(function (a) { return a[0]; }); }, { filtro: st.filtroAutor, rot: function (v) { return autorRot[v] || v; } }));
      listaRadios("tema", opcoes("tema", function (x) { return x.te; }));
      listaRadios("situ", opcoes("situ", function (x) { return [x.si]; }, { todos: "Todas" }));
      listaRadios("orgao", opcoes("orgao", function (x) { return [x.og]; }));
      listaRadios("regime", opcoes("regime", function (x) { return [x.rg]; }));
      listaRadios("aprec", opcoes("aprec", function (x) { return [x.ap]; }, { todos: "Todas" }));
    });
    renderTipos(tpF.cont);

    var ord = st.ordem;
    var lista = filtrados.slice().sort(
      ord === "antigas" ? function (a, b) { return a.dt.localeCompare(b.dt) || a.nu - b.nu; }
        : ord === "movimentacao" ? function (a, b) { return b.ul.localeCompare(a.ul) || b.dt.localeCompare(a.dt); }
          : function (a, b) { return b.dt.localeCompare(a.dt) || b.nu - a.nu; });
    var raizResultados = document.getElementById("pq-resultados");
    trocar(raizResultados.querySelector("[data-lista-resultados]"), lista.slice(0, st.limite).map(cartao));
    raizResultados.querySelector("[data-sem-resultados]").hidden = filtrados.length > 0;
    raizResultados.querySelector("[data-mais]").hidden = filtrados.length <= st.limite;
    raizResultados.querySelectorAll("[data-ordem]").forEach(function (b) {
      var on = b.dataset.ordem === ord;
      b.classList.toggle("botao--primario", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });

    var chips = chipsAtivos();
    var ativos = raizResultados.querySelector("[data-filtros-ativos]");
    ativos.hidden = !chips.length;
    trocar(ativos, chips.length ? [h("span", { class: "rotulo-mono", texto: "FILTROS_ATIVOS" })].concat(chips.map(function (c) {
      return h("button", { type: "button", class: "chip", "aria-label": "Remover filtro " + c.t, onclick: c.tirar }, [c.t, iconeRemover()]);
    })) : []);

    var url = urlApi();
    var link = raizResultados.querySelector("[data-link-api]");
    link.href = url;
    link.textContent = url.replace("https://dadosabertos.camara.leg.br", "") + " ↗";

    var avancados = ["situ", "orgao", "regime", "aprec", "de", "ate"].filter(function (k) { return f[k]; }).length;
    saida("totalTexto", filtrados.length.toLocaleString("pt-BR") + (filtrados.length === 1 ? " proposição" : " proposições"));
    saida("paginaTexto", filtrados.length ? "EXIBINDO " + Math.min(st.limite, filtrados.length) + " DE " + filtrados.length : "");
    saida("qtdFiltros", chips.length ? chips.length + (chips.length === 1 ? " ATIVO" : " ATIVOS") : "NENHUM ATIVO");
    saida("qtdAvancados", avancados ? avancados + (avancados === 1 ? " ATIVO" : " ATIVOS") : "");
    sincronizarCampos();
  }

  /* Reflete o estado nos campos de texto (ex.: após remover um chip ou limpar). */
  function sincronizarCampos() {
    ["q", "numero", "ano", "de", "ate"].forEach(function (k) {
      var el = form.elements[k];
      if (el && el.value !== st.f[k] && document.activeElement !== el) el.value = st.f[k];
    });
  }

  /* ---------- Eventos do formulário ---------- */
  var limpezas = { numero: function (v) { return v.replace(/\D/g, ""); }, ano: function (v) { return v.replace(/\D/g, "").slice(0, 4); } };
  ["q", "numero", "ano", "de", "ate"].forEach(function (k) {
    form.elements[k].addEventListener("input", function (e) {
      var v = limpezas[k] ? limpezas[k](e.target.value) : e.target.value;
      if (v !== e.target.value) e.target.value = v;
      definir(objeto(k, v));
    });
  });
  form.querySelector('[data-filtro-faceta="autor"]').addEventListener("input", function (e) {
    st.filtroAutor = e.target.value;
    renderizar();
  });
  form.querySelector("[data-limpar]").addEventListener("click", function () {
    st = { f: inicial(), filtroAutor: "", limite: LIMITE, ordem: st.ordem, ac: acInicial(), det: 0, copiado: 0 };
    form.querySelectorAll("input[type=search], input[type=text], input[type=date]").forEach(function (el) { el.value = ""; });
    renderizar();
  });
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var el = document.getElementById("pq-resultados");
    if (el.scrollIntoView) el.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  document.querySelectorAll("[data-ordem]").forEach(function (b) {
    b.addEventListener("click", function () { st.ordem = b.dataset.ordem; st.limite = LIMITE; renderizar(); });
  });
  document.querySelector("[data-mais]").addEventListener("click", function () { st.limite += LIMITE; renderizar(); });

  renderizar();
})();

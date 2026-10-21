/* Interações do relatório de tramitação.
   - Valor compartilhado: hover/foco em um componente com data-valor acende todos com o mesmo valor.
   - Seleção: o último link ou botão de vidro clicado fica marcado (aria-current).
   - Janelas: botões com data-janela abrem o <dialog> correspondente.
   - Popover da versão válida: documentos aprovados (classe "aprovado" + data-origem) o abrem
     no hover/foco; o clique o fixa até ser fechado. */
(function () {
  "use strict";

  var raiz = document.querySelector(".pagina");
  var popover = document.getElementById("popover-versao");
  var tempoFecho = null;
  var fixado = false;
  var acionador = null;

  /* ---------- Valor compartilhado ---------- */
  function acender(valor, ligado) {
    if (!valor) return;
    document.querySelectorAll('[data-valor="' + valor + '"]').forEach(function (el) {
      el.classList.toggle("aceso", ligado);
    });
  }

  function componente(alvo) {
    return alvo && alvo.closest ? alvo.closest("[data-valor]") : null;
  }

  /* Dentro das janelas o popover ficaria sob a camada do <dialog>: só acende. */
  function acionaPopover(el) {
    return el.dataset.origem && !el.closest("dialog");
  }

  ["mouseover", "focusin"].forEach(function (tipo) {
    document.addEventListener(tipo, function (e) {
      var el = componente(e.target);
      if (!el) return;
      acender(el.dataset.valor, true);
      if (acionaPopover(el)) abrirPopover(el, false);
    });
  });
  ["mouseout", "focusout"].forEach(function (tipo) {
    document.addEventListener(tipo, function (e) {
      var el = componente(e.target);
      if (!el || (e.relatedTarget && el.contains(e.relatedTarget))) return;
      acender(el.dataset.valor, false);
      if (acionaPopover(el)) agendarFecho();
    });
  });

  /* ---------- Seleção ---------- */
  function selecionar(el) {
    document.querySelectorAll(".selecionado").forEach(function (outro) {
      outro.classList.remove("selecionado");
      outro.removeAttribute("aria-current");
    });
    el.classList.add("selecionado");
    el.setAttribute("aria-current", "true");
  }

  /* ---------- Janelas ---------- */
  function abrirJanela(id) {
    var janela = id && document.getElementById(id);
    if (!janela || typeof janela.showModal !== "function") return;
    fecharPopover();
    janela.showModal();
  }

  document.querySelectorAll("dialog.janela").forEach(function (janela) {
    // Clique no véu (fora da caixa) fecha a janela.
    janela.addEventListener("click", function (e) {
      if (e.target === janela) janela.close();
    });
  });

  document.addEventListener("click", function (e) {
    var fechar = e.target.closest("[data-fechar]");
    if (fechar) {
      fechar.closest("dialog").close();
      return;
    }
    if (e.target.closest("[data-fechar-popover]")) {
      fecharPopover();
      return;
    }
    if (e.target.closest("[data-ver-detalhes]")) {
      abrirJanela(janelaDetalhes());
      return;
    }
    var el = e.target.closest(".liquido, .liquido-inline");
    if (!el || el.closest("dialog, .popover")) return;
    selecionar(el);
    if (el.dataset.origem) {
      // Documento aprovado: fixa o popover; links continuam abrindo o PDF.
      abrirPopover(el, true);
    } else if (el.dataset.janela) {
      abrirJanela(el.dataset.janela);
    }
  });

  /* ---------- Popover da versão válida ---------- */
  function cancelarFecho() {
    if (tempoFecho) {
      clearTimeout(tempoFecho);
      tempoFecho = null;
    }
  }

  function agendarFecho() {
    cancelarFecho();
    tempoFecho = setTimeout(function () {
      if (!fixado) fecharPopover();
    }, 180);
  }

  function fecharPopover() {
    cancelarFecho();
    if (!popover) return;
    popover.hidden = true;
    fixado = false;
    acionador = null;
  }

  function janelaDetalhes() {
    if (acionador && acionador.dataset.detalhe) return acionador.dataset.detalhe;
    var no = document.querySelector('.arvore__no[data-valor="' + popover.dataset.valorVersao + '"]');
    return no ? no.dataset.detalhe || no.dataset.janela : "janela-raiz";
  }

  /* Posiciona o popover junto ao componente, sem sair da largura da tela. */
  function abrirPopover(el, fixar) {
    if (!popover || (!fixar && fixado)) {
      cancelarFecho();
      return;
    }
    cancelarFecho();
    fixado = fixado || fixar;
    acionador = el;
    popover.querySelector("[data-origem-texto]").textContent = el.dataset.origem;

    var r = el.getBoundingClientRect();
    var rr = raiz.getBoundingClientRect();
    var vw = document.documentElement.clientWidth || window.innerWidth;
    var vh = window.innerHeight;
    var largura = Math.min(640, vw - 32);
    var esquerda = Math.max(16, Math.min(r.left + r.width / 2 - largura / 2, vw - largura - 16));
    var abaixo = vh - r.bottom;
    var acima = abaixo < 380 && r.top > abaixo;
    var seta = Math.max(18, Math.min(r.left + r.width / 2 - esquerda - 7, largura - 32));
    var topo = (acima ? r.top - 12 : r.bottom + 12) - rr.top;

    popover.style.left = Math.round(esquerda - rr.left) + "px";
    popover.style.top = Math.round(topo) + "px";
    popover.style.width = Math.round(largura) + "px";
    popover.style.maxHeight = Math.round(Math.max(240, (acima ? r.top : abaixo) - 28)) + "px";
    popover.style.transform = acima ? "translateY(-100%)" : "";
    popover.classList.toggle("popover--acima", acima);

    var ponta = popover.querySelector(".popover__seta");
    ponta.className = "popover__seta " + (acima ? "popover__seta--base" : "popover__seta--topo");
    ponta.style.left = Math.round(seta) + "px";
    popover.hidden = false;
  }

  if (popover) {
    popover.addEventListener("mouseenter", cancelarFecho);
    popover.addEventListener("focusin", cancelarFecho);
    popover.addEventListener("mouseleave", agendarFecho);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !popover.hidden) fecharPopover();
    });
    // Clique fora do popover fixado o fecha.
    document.addEventListener("pointerdown", function (e) {
      if (fixado && !popover.contains(e.target) && !(acionador && acionador.contains(e.target))) fecharPopover();
    });
  }
})();

// A chemical formula, oxide or ion written as a chemist writes it — shared by the review page and the spectrum window.
//   chemNodes('Ca(UO2)2(PO4)2·11H2O')  →  Ca(UO<sub>2</sub>)<sub>2</sub>(PO<sub>4</sub>)<sub>2</sub>·11H<sub>2</sub>O   (a DocumentFragment)
//   chemNodes('(SO4)2−')               →  (SO<sub>4</sub>)<sup>2−</sup>;   'Fe3+' → Fe<sup>3+</sup>;   'SO4 ν3' → SO<sub>4</sub> ν3
// The rule (mirrored by pxrd_review.bands.chem_tokens, which the Word export uses): a number after a Latin letter, ')' or
// ']' is a subscript; a charge — digits and + or − — after a letter, ')' or ']' is a superscript; a number after '·' (the
// water count), after Σ or after a Greek letter (ν3) stays as it is. Only formula fields go through it, never prose: 'R1'
// would come out R₁.
(function () {
  const TOKEN = /(?<=[A-Za-z)\]])(\d*[+−]|\d+-(?![A-Za-z]))|(?<=[A-Za-z)\]])(\d+(?:\.\d+)?)/g;
  function chemTokens(text) {                         // [[kind, text]] with kind '', 'sub' or 'sup'
    const out = []; let last = 0;
    for (const m of String(text == null ? '' : text).matchAll(TOKEN)) {
      if (m.index > last) out.push(['', text.slice(last, m.index)]);
      out.push([m[1] != null ? 'sup' : 'sub', m[0]]); last = m.index + m[0].length;
    }
    if (last < String(text).length) out.push(['', String(text).slice(last)]);
    return out;
  }
  function chemNodes(text) {                          // HTML nodes
    const frag = document.createDocumentFragment();
    for (const [kind, t] of chemTokens(text)) {
      if (!kind) frag.append(document.createTextNode(t));
      else { const e = document.createElement(kind); e.textContent = t; frag.append(e); }
    }
    return frag;
  }
  function chemSvg(textEl, text) {                    // the same inside an SVG <text>: tspans shifted, three-quarter size
    const ns = 'http://www.w3.org/2000/svg';
    for (const [kind, t] of chemTokens(text)) {
      if (!kind) { textEl.append(document.createTextNode(t)); continue; }
      const ts = document.createElementNS(ns, 'tspan');
      ts.setAttribute('font-size', '75%'); ts.setAttribute('dy', kind === 'sub' ? '0.3em' : '-0.45em'); ts.textContent = t;
      textEl.append(ts);
      const back = document.createElementNS(ns, 'tspan'); back.setAttribute('dy', kind === 'sub' ? '-0.3em' : '0.45em'); back.textContent = '​';
      textEl.append(back);                            // the baseline put back for what follows
    }
    return textEl;
  }
  window.chemTokens = chemTokens; window.chemNodes = chemNodes; window.chemSvg = chemSvg;
})();

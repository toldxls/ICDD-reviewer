// A chemical formula, oxide or ion written as a chemist writes it — shared by the review page and the spectrum window.
//   chemNodes('Ca(UO2)2(PO4)2·11H2O')  →  Ca(UO<sub>2</sub>)<sub>2</sub>(PO<sub>4</sub>)<sub>2</sub>·11H<sub>2</sub>O   (a DocumentFragment)
//   chemNodes('(SO4)2−')               →  (SO<sub>4</sub>)<sup>2−</sup>;   'Fe3+' → Fe<sup>3+</sup>;   'SO4 ν3' → SO<sub>4</sub> ν3
// The rule (mirrored by pxrd_review.bands.chem_tokens, which the Word export uses): a number after a Latin letter, ')' or
// ']' is a subscript; a charge — digits and + or − — after a letter, ')' or ']' is a superscript; a number after '·' (the
// water count), after Σ or after a Greek letter (ν3) stays as it is. Only formula fields go through it, never prose: 'R1'
// would come out R₁.
(function () {
  // a charge: digits and + or − after a letter or a bracket ('Fe3+', '(SO4)2−'); the ASCII hyphen only after a bracket ('(SO4)2-' — after a
  // letter '3-' is a range, 'Pb3-x'); a count right after a charge is a subscript ('Fe2+2O3'); otherwise a number after a letter or bracket
  const TOKEN = /(?<=[A-Za-z)\]])(\d*[+−]|(?<=[)\]])\d*-)(\d+(?:\.\d+)?)?|(?<=[A-Za-z)\]])(\d+(?:\.\d+)?)/g;
  function chemTokens(text) {                         // [[kind, text]] with kind '', 'sub' or 'sup'
    const s = String(text == null ? '' : text), out = []; let last = 0;
    for (const m of s.matchAll(TOKEN)) {
      if (m.index > last) out.push(['', s.slice(last, m.index)]);
      if (m[1] != null) { out.push(['sup', m[1]]); if (m[2]) out.push(['sub', m[2]]); }
      else out.push(['sub', m[3]]);
      last = m.index + m[0].length;
    }
    if (last < s.length) out.push(['', s.slice(last)]);
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
      // the baseline put back for what follows: the shift was in the small tspan's em (0.75 of the text's), the return is in the text's own
      const back = document.createElementNS(ns, 'tspan'); back.setAttribute('dy', kind === 'sub' ? '-0.225em' : '0.3375em'); back.textContent = '​';
      textEl.append(back);
    }
    return textEl;
  }
  window.chemTokens = chemTokens; window.chemNodes = chemNodes; window.chemSvg = chemSvg;
})();

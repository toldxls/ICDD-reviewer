"""Build data/ff_it92.json.gz — X-ray scattering-factor coefficients (International Tables Vol. C,
Table 6.1.1.4: the Cromer–Mann a1–a4, b1–b4, c) for neutral atoms and the ions the table gives, read
from gemmi at DEV time. The shipped tool reads the JSON only (the same pattern as data/symops.json.gz:
gemmi is a dev-time dependency, never a runtime one).

    python3 tools/build_ff.py
"""
import os, json, gzip
import gemmi

out = {}
gemmi.IT92_set_ignore_charge(False)
for z in range(1, 99):
    el = gemmi.Element(z)
    c = el.it92
    if c is None:
        continue
    out[el.name] = {'a': list(c.a), 'b': list(c.b), 'c': c.c}
    for ch in range(-3, 8):
        if ch == 0:
            continue
        ci = gemmi.IT92_get_exact(el, ch)
        if ci is not None:
            out['%s%d%s' % (el.name, abs(ch), '+' if ch > 0 else '-')] = {'a': list(ci.a), 'b': list(ci.b), 'c': ci.c}
path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'pxrd_review', 'data', 'ff_it92.json.gz')
with gzip.open(path, 'wt', encoding='utf-8') as f:
    json.dump({'source': 'International Tables for Crystallography Vol. C (1992), Table 6.1.1.4, via gemmi %s' % gemmi.__version__,
               'form': 'f(s) = sum_i a_i exp(-b_i s^2) + c, s = sin(theta)/lambda', 'coefs': out}, f)
print(path, len(out), 'entries')

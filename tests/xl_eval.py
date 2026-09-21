"""A small evaluator for the formulas pxrd_review writes into its workbooks — enough to prove in a
test that a sheet's live formulas give the numbers the Python gave. Not a spreadsheet engine: cell
and range references (other sheets too), arithmetic, and SUM / SUMIF / SUMPRODUCT / AVERAGE /
STDEV / MIN / MAX / ABS / IF / EXP / TEXT and & (joining text), whole-column ranges (bonds!A:A) and quoted sheet names."""
import re, math, statistics
import openpyxl
from openpyxl.utils import range_boundaries

_REF = re.compile(r"(?:(?:'([^']+)'|(\w+))!)?(?:(\$?[A-Z]{1,2}\$?\d+)(?::(\$?[A-Z]{1,2}\$?\d+))?|([A-Z]{1,2}):([A-Z]{1,2})(?![A-Za-z(]))")

def _flat(args):
    out = []
    for a in args:
        out += _flat(a) if isinstance(a, list) else [a]
    return out

def _nums(args):
    return [v for v in _flat(args) if isinstance(v, (int, float)) and not isinstance(v, bool)]

def _sumif(rng, crit, vals):
    return sum(v for k, v in zip(rng, vals) if k == crit and isinstance(v, (int, float)))

_FUNCS = {'SUM': lambda *a: sum(_nums(a)), 'AVERAGE': lambda *a: statistics.mean(_nums(a)), 'STDEV': lambda *a: statistics.stdev(_nums(a)),
          'MIN': lambda *a: min(_nums(a)), 'MAX': lambda *a: max(_nums(a)), 'ABS': abs, 'EXP': math.exp, 'MEDIAN': lambda *a: statistics.median(_nums(a)) if _nums(a) else 0, 'COUNT': lambda *a: len(_nums(a)),
          'INDEX': lambda rng, i: rng[int(i) - 1] if i else '#N/A', 'MATCH': lambda v, rng, _t=0: (rng.index(v) + 1) if v in rng else 0,   # IF is eager here, lazy in Excel: an unused branch must not raise
          'LEFT': lambda t, n_: str(t)[:int(n_)],
          '_AND': lambda *a: all(a), '_OR': lambda *a: any(a), 'TEXT': lambda v, f: _text(v, f), 'IF': lambda c, a, b: a if c else b, 'SUMIF': _sumif,
          'SUMPRODUCT': lambda x, y: sum(p * q for p, q in zip(x, y) if isinstance(p, (int, float)) and isinstance(q, (int, float)))}

def _text(v, f):
    f0 = f.split(';')[0]
    d = f0.split('.')[1] if '.' in f0 else ''
    out = '%.*f' % (len(d), v)
    if '#' in d:
        out = out.rstrip('0').rstrip('.')
    return ('+' if f0.startswith('+') and v >= 0 else '') + out

class Book:
    def __init__(self, path):
        self.wb = openpyxl.load_workbook(path); self.memo = {}
    def value(self, sheet, ref):
        key = (sheet, ref.replace('$', ''))
        if key not in self.memo:
            self.memo[key] = None                                      # a circular reference reads as blank rather than recursing
            v = self.wb[sheet][key[1]].value
            self.memo[key] = self._eval(sheet, v[1:]) if isinstance(v, str) and v.startswith('=') else v
        return self.memo[key]
    def _eval(self, sheet, expr):
        env = dict(_FUNCS); n = [0]
        def sub(m):
            sh = m.group(1) or m.group(2) or sheet; name = '_r%d' % n[0]; n[0] += 1
            if m.group(5):                                             # a whole column: down to the sheet's last row
                ws = self.wb[sh]
                env[name] = [self.value(sh, '%s%d' % (m.group(5), r)) for r in range(1, ws.max_row + 1)]
            elif m.group(4):
                c1, r1, c2, r2 = range_boundaries((m.group(3) + ':' + m.group(4)).replace('$', ''))
                env[name] = [self.value(sh, self.wb[sh].cell(r, c).coordinate) for r in range(r1, r2 + 1) for c in range(c1, c2 + 1)]
            else:
                v = self.value(sh, m.group(3)); env[name] = 0 if v is None else v
            return name
        parts = re.split(r'("[^"]*")', expr)                           # references are not looked for inside strings
        code = ''.join(p if p.startswith('"') else _REF.sub(sub, p).replace('<>', '!=').replace('^', '**').replace('&', '+').replace('AND(', '_AND(').replace('OR(', '_OR(') for p in parts)
        code = re.sub(r'(?<![<>!=])=(?!=)', '==', code)
        return eval(code, {'__builtins__': {}}, env)

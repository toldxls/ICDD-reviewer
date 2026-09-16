"""Reduced cells — the one form a lattice has, whatever setting a paper, a .cif or Mindat chose.

`niggli(a, b, c, α, β, γ)` returns the Niggli-reduced cell (Křivý & Gruber 1976, with the
Grosse-Kunstleve, Sauter & Adams 2004 tolerances); `primitive(cell, centring)` turns a
conventional A/B/C/I/F/R cell into a primitive one first; `same_lattice(cell1, cell2, c1, c2)`
says whether two conventional cells describe one lattice — two settings of a monoclinic cell
(a and c swapped, β and its supplement), an I- against a C-setting, a rhombohedral against a
hexagonal cell — which the sorted-axes comparison the checks use cannot tell from a
discrepancy. Cells are (a, b, c, α, β, γ) in Å and degrees."""
import math


def _metric(cell):
    a, b, c, al, be, ga = cell
    ca, cb, cg = (math.cos(math.radians(x)) for x in (al, be, ga))
    return [[a * a, a * b * cg, a * c * cb], [a * b * cg, b * b, b * c * ca], [a * c * cb, b * c * ca, c * c]]


def _cell_of(G):
    a, b, c = (math.sqrt(G[i][i]) for i in range(3))
    al = math.degrees(math.acos(max(-1.0, min(1.0, G[1][2] / (b * c)))))
    be = math.degrees(math.acos(max(-1.0, min(1.0, G[0][2] / (a * c)))))
    ga = math.degrees(math.acos(max(-1.0, min(1.0, G[0][1] / (a * b)))))
    return (a, b, c, al, be, ga)


def _transform(G, M):
    """G' = M G Mᵀ for a basis change a' = M a (rows of M give the new axes in the old basis)."""
    out = [[0.0] * 3 for _ in range(3)]
    for i in range(3):
        for j in range(3):
            out[i][j] = sum(M[i][p] * G[p][q] * M[j][q] for p in range(3) for q in range(3))
    return out


_CENTRING = {
    'P': [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
    'A': [[1, 0, 0], [0, 0.5, 0.5], [0, -0.5, 0.5]],
    'B': [[0.5, 0, 0.5], [0, 1, 0], [-0.5, 0, 0.5]],
    'C': [[0.5, 0.5, 0], [-0.5, 0.5, 0], [0, 0, 1]],
    'I': [[-0.5, 0.5, 0.5], [0.5, -0.5, 0.5], [0.5, 0.5, -0.5]],
    'F': [[0, 0.5, 0.5], [0.5, 0, 0.5], [0.5, 0.5, 0]],
    'R': [[2 / 3, 1 / 3, 1 / 3], [-1 / 3, 1 / 3, 1 / 3], [-1 / 3, -2 / 3, 1 / 3]],   # the hexagonal (obverse) setting's rhombohedral primitive
}


def primitive(cell, centring='P'):
    """The primitive cell of a conventional centred cell (the metric of a primitive basis)."""
    M = _CENTRING.get((centring or 'P').upper()[:1], _CENTRING['P'])
    return _cell_of(_transform(_metric(cell), M))


def niggli(a, b, c, al, be, ga, eps=1e-5, max_iter=100):
    """The Niggli-reduced cell of a (primitive) cell — Křivý & Gruber's algorithm on the metric
    (A, B, C, ξ, η, ζ) = (a², b², c², 2bc·cosα, 2ac·cosβ, 2ab·cosγ)."""
    A, B, C = a * a, b * b, c * c
    xi = 2 * b * c * math.cos(math.radians(al)); eta = 2 * a * c * math.cos(math.radians(be)); zeta = 2 * a * b * math.cos(math.radians(ga))
    e = eps * (A * B * C) ** (1 / 3)
    def lt(x, y): return x < y - e
    def gt(x, y): return x > y + e
    def eq(x, y): return abs(x - y) <= e
    for _ in range(max_iter):
        if gt(A, B) or (eq(A, B) and gt(abs(xi), abs(eta))):                    # A1
            A, B = B, A; xi, eta = eta, xi
        if gt(B, C) or (eq(B, C) and gt(abs(eta), abs(zeta))):                  # A2
            B, C = C, B; eta, zeta = zeta, eta
            continue
        # A3 / A4: all three angle terms positive when their product is (type I), else all
        # non-positive (type II) — Gruber's rule, a zero term counting as either
        nz = [v for v in (xi, eta, zeta) if not eq(v, 0)]
        if len(nz) == 3 and (xi * eta * zeta) > 0:
            xi, eta, zeta = abs(xi), abs(eta), abs(zeta)
        else:
            xi, eta, zeta = -abs(xi), -abs(eta), -abs(zeta)
        if gt(abs(xi), B) or (eq(xi, B) and lt(2 * eta, zeta)) or (eq(xi, -B) and lt(zeta, 0)):     # A5
            sg = 1 if xi > 0 else -1
            C = B + C - xi * sg; eta = eta - zeta * sg; xi = xi - 2 * B * sg
            continue
        if gt(abs(eta), A) or (eq(eta, A) and lt(2 * xi, zeta)) or (eq(eta, -A) and lt(zeta, 0)):    # A6
            sg = 1 if eta > 0 else -1
            C = A + C - eta * sg; xi = xi - zeta * sg; eta = eta - 2 * A * sg
            continue
        if gt(abs(zeta), A) or (eq(zeta, A) and lt(2 * xi, eta)) or (eq(zeta, -A) and lt(eta, 0)):   # A7
            sg = 1 if zeta > 0 else -1
            B = A + B - zeta * sg; xi = xi - eta * sg; zeta = zeta - 2 * A * sg
            continue
        if lt(xi + eta + zeta + A + B, 0) or (eq(xi + eta + zeta + A + B, 0) and gt(2 * (A + eta) + zeta, 0)):   # A8
            C = A + B + C + xi + eta + zeta; xi = 2 * B + xi + zeta; eta = 2 * A + eta + zeta
            continue
        break
    a_, b_, c_ = math.sqrt(A), math.sqrt(B), math.sqrt(C)
    al_ = math.degrees(math.acos(max(-1.0, min(1.0, xi / (2 * b_ * c_)))))
    be_ = math.degrees(math.acos(max(-1.0, min(1.0, eta / (2 * a_ * c_)))))
    ga_ = math.degrees(math.acos(max(-1.0, min(1.0, zeta / (2 * a_ * b_)))))
    return (a_, b_, c_, al_, be_, ga_)


def reduced(cell, centring='P'):
    """The Niggli cell of a conventional cell with the given centring letter."""
    return niggli(*primitive(cell, centring))


def same_lattice(cell1, cell2, centring1='P', centring2='P', tol=0.01, angle_tol=1.0):
    """Whether two conventional cells describe one lattice: their reduced cells agree on every
    length within `tol` (relative) and every angle within `angle_tol` degrees."""
    try:
        r1, r2 = reduced(cell1, centring1), reduced(cell2, centring2)
    except (ValueError, ZeroDivisionError):
        return False
    return all(abs(x - y) <= tol * max(x, y) for x, y in zip(r1[:3], r2[:3])) and all(abs(x - y) <= angle_tol for x, y in zip(r1[3:], r2[3:]))


def centring_of(symbol):
    """The lattice letter of a Hermann–Mauguin symbol ('C2/c' -> 'C'; 'R-3m' -> 'R'); 'P' when none."""
    s = (symbol or '').strip()
    return s[0].upper() if s and s[0].upper() in 'PABCIFR' else 'P'

"""Unit tests for pxrd_review.cif_audit and pxrd_review.checkcif — synthetic .cif, .res, .docx and report text.

    python3 -m unittest tests.test_cif_audit -v
"""
import os, re, shutil, tempfile, unittest

from pxrd_review import cif_audit as CA, checkcif as CC, bv_check as B

# a P1 box: Mg1 at the origin, O1 2.0 Å along a, a water OW1 4.0 Å along b with H1 0.96 Å from it
CIF = """data_test
_chemical_name_mineral testite
_chemical_formula_sum 'Mg O2 H2'
_cell_length_a 8
_cell_length_b 8
_cell_length_c 8
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_cell_volume 512
_cell_formula_units_z 1
_space_group_name_H-M_alt 'P 1'
_exptl_crystal_density_diffrn 1.9
_exptl_absorpt_coefficient_mu 1.234
_exptl_crystal_F_000 40
_diffrn_reflns_number 1000
_diffrn_reflns_av_R_equivalents 0.0310
_diffrn_reflns_theta_max 27.50
_reflns_number_total 500
_reflns_number_gt 450
_refine_ls_number_reflns 500
_refine_ls_number_parameters 30
_refine_ls_number_restraints 2
_refine_ls_R_factor_all 0.0456
_refine_ls_R_factor_gt 0.0396
_refine_ls_wR_factor_ref 0.0666
_refine_ls_wR_factor_gt 0.0647
_refine_ls_goodness_of_fit_ref 1.130
loop_
_space_group_symop_operation_xyz
'x, y, z'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
_atom_site_U_iso_or_equiv
Mg1 Mg 0 0 0 0.010
O1 O 0.25 0 0 0.015
OW1 O 0 0.5 0 0.030
H1 H 0 0.62 0 0.036
_shelx_res_file
;
TITL test
CELL 0.71073 8 8 8 90 90 90
ZERR 1 0 0 0 0 0 0
SFAC Mg O H
UNIT 1 2 2
MG1   1   0.000000  0.000000  0.000000  11.00000  0.01000
O1    2   0.250000  0.000000  0.000000  11.00000  0.01500
H1    3   0.000000  0.620000  0.000000  11.00000 -1.20000
OW1   2   0.000000  0.500000  0.000000  11.00000  0.03000
HKLF 4
END
;
"""


def _docx(path, items):
    """items: [('p', text)] or [('table', [cells])]"""
    from docx import Document
    doc = Document()
    for kind, x in items:
        if kind == 'p':
            doc.add_paragraph(x)
        else:
            t = doc.add_table(rows=0, cols=len(x))
            for i, c in enumerate(t.add_row().cells):
                c.text = x[i]
    doc.save(path)
    return path


class Audit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='cifaudit_')
        self.cif = os.path.join(self.tmp, 't.cif')
        with open(self.cif, 'w', encoding='utf-8') as f:
            f.write(CIF)
        self.st = B.Structure(self.cif)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_riding_h_listed_after_the_wrong_atom(self):
        recs = CA.check_riding(self.st)
        self.assertEqual(len(recs), 1, recs)
        self.assertIn('H1 rides on O1', recs[0]['text']); self.assertIn('bonded to OW1 (0.96 Å', recs[0]['text'])
        self.assertIn('Ueq 0.0150', recs[0]['text']); self.assertIn('Ueq 0.0300', recs[0]['text'])
        self.assertEqual([a[0] for a in CA.res_atoms(self.st)], ['MG1', 'O1', 'H1', 'OW1'])

    def test_numbers_table_prose_anchor_history(self):
        d = _docx(os.path.join(self.tmp, 'm.docx'), [
            ('table', ['Final R indices [I > 2σI]', 'R1 = 0.0450, wR2 = 0.0647']),          # the table differs: flag
            ('table', ['R indices (all data)', 'R1 = 0.0456, wR2 = 0.0666']),              # agrees
            ('table', ['Reflections collected/unique', '1000/500; Rint = 0.0310']),
            ('table', ['Parameters/restraints', '30/2']),
            ('p', 'Crystal structure: R1 = 0.0420 for 450 unique reflections with I > 2σI.'),   # the .cif's own count: flag
            ('p', 'At this stage the refinement converged to R1 = 0.0410.'),                   # near, unanchored: note
            ('p', 'The related mineral otherite refined to R1 = 0.085.'),                       # far: ignored
            ('p', 'Unit-cell parameters refined from powder data:'),
            ('p', 'a = 8.05(2) Å'),                                                             # the powder cell: ignored
            ('table', ['Unit cell dimensions', 'a = 8.0000(5) Å']),
        ])
        recs = CA.check_numbers(self.st, CA.docx_lines(d))
        flags = [r for r in recs if r['severity'] == 'flag']; notes = [r for r in recs if r['severity'] == 'note']
        self.assertEqual(len(flags), 2, recs)
        self.assertTrue(any('the table gives 0.0450' in r['text'] for r in flags), recs)
        self.assertTrue(any("the .cif's own 450 reflections gives 0.0420" in r['text'] for r in flags), recs)
        self.assertEqual(len(notes), 1, recs); self.assertIn('0.0410', notes[0]['text'])
        self.assertIn('8 kinds read', recs[0]['text']); self.assertIn('Rint', recs[0]['text']); self.assertTrue(recs[0]['text'].rstrip('; 3 differ').endswith('a)'), recs[0]['text'])

    def test_a_prose_repeat_never_hides_the_table_flag(self):
        d = _docx(os.path.join(self.tmp, 'm.docx'), [('p', 'The structure refined to R1 = 0.0450 at an early stage.'),
                                                       ('table', ['Final R indices [I > 2σI]', 'R1 = 0.0450, wR2 = 0.0647'])])
        recs = [r for r in CA.check_numbers(self.st, CA.docx_lines(d)) if r['kind'] == 'number']
        self.assertEqual([r['severity'] for r in recs], ['flag'], recs)                      # the table's, judged first

    def test_density_from_the_ideal_formula(self):
        # Mg(OH)2 · … : the ideal formula's mass 58.32 with Z = 1 in 512 Å³ gives 0.189 g/cm³
        d = _docx(os.path.join(self.tmp, 'm.docx'), [
            ('p', 'Ideal formula: Mg(OH)2'),
            ('p', 'Density (calc.) = 0.189 g·cm–3 for the ideal formula.'),                    # right
            ('table', ['Density (for above formula)', '1.900 g cm–3']),                        # the .cif's own, H-less density
            ('p', 'Density (calc.) = 0.210 g·cm–3 for the empirical formula.'),                # not this check's
        ])
        recs = CA.check_density(self.st, CA.docx_lines(d))
        flags = [r for r in recs if 'stated, but' in r['text']]
        self.assertEqual(len(flags), 1, recs)
        self.assertIn('1.900 stated', flags[0]['text']); self.assertIn("the .cif's own _exptl_crystal_density_diffrn", flags[0]['text'])
        self.assertTrue(any('0.189 and 1.900 in different places' in r['text'] for r in recs), recs)

    def test_site_labels_named_in_the_prose(self):
        d = _docx(os.path.join(self.tmp, 'm.docx'), [
            ('p', 'The O1 site bridges Mg1 and Mg2, while OW1 is a water molecule.'),         # Mg2: no such site
            ('p', 'Compare hörnesite, Mg3(AsO4)2·8H2O, and the reaction 2Mg + O2 → 2MgO.'),   # formulas, not sites
            ('p', 'The structure was refined in space group P1 with Mg2+ at the origin.'),
            ('p', 'Sheldrick, G.M. (2015) Crystal structure refinement with SHELXL. Acta Crystallographica, C71, 3–8.'),
            ('p', 'The Ow1 site accepts a hydrogen bond from H1.'),                            # case: the .cif's OW1
        ])
        recs = CA.check_labels(self.st, CA.docx_lines(d))
        self.assertEqual([re.search(r'site (\w+)', r['text']).group(1) for r in recs], ['Mg2'], recs)

    def test_audit_lines_and_checkcif(self):
        rep = os.path.join(self.tmp, 'r.txt')
        with open(rep, 'w', encoding='utf-8') as f:
            f.write('PLAT965_ALERT_2_G The Weighting Scheme has not converged\n'
                    'PLAT975_ALERT_2_C Check Calcd Resid. Dens.  0.91Ang From Ow1     .       0.43 eA-3\n'
                    'PLAT976_ALERT_2_C Check Calcd Resid. Dens.  0.88Ang From Ow1     .      -0.52 eA-3\n'
                    'PLAT975_ALERT_2_C Check Calcd Resid. Dens.  1.40Ang From Mg1     .       0.40 eA-3\n'
                    'PUBL005_ALERT_1_A _publ_section_abstract missing\n')
        res = CC.audit(CC.parse(CC.read_text(rep)))
        self.assertEqual(res['tally'], {'A': 1, 'B': 0, 'C': 3, 'G': 1})
        self.assertEqual([e[0] for e in res['elevated']], ['CRITICAL'])
        self.assertEqual([(d, a) for d, a, _ in res['h_peaks']], [(0.91, 'Ow1')])     # a peak at an O–H distance; not the hole, not the Mg
        self.assertEqual(res['demoted'], 1)
        out = CA.audit(self.cif, None, rep)
        self.assertTrue(any('H1 rides on O1' in ln for ln in out['lines']))
        self.assertTrue(any(ln.startswith('  CRITICAL PLAT965') for ln in out['lines']), out['lines'])


# a P-1 cell (two operators): a shared Fe/Mg site fixed by hand at 0.31 + 0.225 (partial, not over-occupied), a split O5A/O5B pair
# 0.5 Å apart refined on two free variables, a Ca on an inversion centre (sof 10.5 is a full site), the refinement's
# transmission range wider than μ and the crystal allow, and a BASF the manuscript denies
CIF_OCC = CIF.replace("_space_group_name_H-M_alt 'P 1'", "_space_group_name_H-M_alt 'P -1'").replace("'x, y, z'\n", "'x, y, z'\n'-x, -y, -z'\n") \
    .replace("H1 H 0 0.62 0 0.036\n", "H1 H 0 0.62 0 0.036\nFe1 Fe 0.3 0.2 0.1 0.010\nMg2 Mg 0.3 0.2 0.1 0.010\nO5A O 0.30 0.30 0.30 0.020\nO5B O 0.34 0.34 0.30 0.020\nCa1 Ca 0 0 0.5 0.012\n") \
    .replace("_exptl_absorpt_coefficient_mu 1.234\n", "_exptl_absorpt_coefficient_mu 1.234\n_exptl_absorpt_correction_type analytical\n_exptl_crystal_size_max 0.10\n_exptl_absorpt_correction_T_min 0.40\n_exptl_absorpt_correction_T_max 0.95\n") \
    .replace("SFAC Mg O H\nUNIT 1 2 2\n", "SFAC MG O H FE CA\nUNIT 2 4 4 2 2\nFVAR 0.5 0.62 0.30\nBASF 0.23\n") \
    .replace("MG1   1   0.000000  0.000000  0.000000  11.00000  0.01000\n", "MG1   1   0.000000  0.000000  0.000000  10.50000  0.01000\n") \
    .replace("OW1   2   0.000000  0.500000  0.000000  11.00000  0.03000\n",
             "OW1   2   0.000000  0.500000  0.000000  10.50000  0.03000\nFE1   4   0.300000  0.200000  0.100000  10.31000  0.01000\nMG2   1   0.300000  0.200000  0.100000  10.22500  0.01000\n"
             "O5A   2   0.300000  0.300000  0.300000  21.00000  0.02000\nO5B   2   0.340000  0.340000  0.300000  31.00000  0.02000\nCA1   5   0.000000  0.000000  0.500000  10.50000  0.01200\n")


class Occupancies(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='cifocc_')
        self.cif = os.path.join(self.tmp, 'o.cif')
        with open(self.cif, 'w', encoding='utf-8') as f:
            f.write(CIF_OCC)
        self.st = B.Structure(self.cif)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_res_model_reads_upper_case_sfac_and_codes(self):
        m = CA.res_model(self.st)
        self.assertEqual(m['fvar'], [0.5, 0.62, 0.30]); self.assertEqual(m['basf'], [0.23])
        els = {a['label']: a['element'] for a in m['atoms']}
        self.assertEqual((els['FE1'], els['CA1'], els['MG2']), ('Fe', 'Ca', 'Mg'))
        self.assertEqual(CA.sof_value(10.31, m['fvar']), (0.31, 'fixed', None))
        self.assertEqual(CA.sof_value(21.0, m['fvar']), (0.62, 'fv', 2))
        v, kind, k = CA.sof_value(-21.0, m['fvar']); self.assertAlmostEqual(v, 0.38); self.assertEqual((kind, k), ('1-fv', 2))

    def test_occupancies(self):
        recs = CA.check_occupancies(self.st)
        texts = [r['text'] for r in recs]
        # Fe1/Mg1 share a general position (sym factor 1): 0.31 + 0.225 fixed… no: the site is general, sof = occupancy
        over = [r for r in recs if r['severity'] == 'flag']
        self.assertEqual(over, [], texts)                                  # 0.31 + 0.225 = 0.535: not over-occupied
        self.assertTrue(any(t.startswith('occupancies fixed, not refined: FE1 0.310, MG2 0.225') for t in texts), texts)
        self.assertTrue(any(t.startswith('split pair O5A/O5B') and 'adding to 0.920' in t for t in texts), texts)   # fv2 0.62 + fv3 0.30, two free variables
        self.assertFalse(any('CA1' in t for t in texts), texts)            # sof 10.5 on the inversion centre is a full site

    def test_refinement_triage(self):
        recs = CA.check_refinement(self.st, [('p', 'The crystal was examined and no twinning was observed.')])
        flags = [r['text'] for r in recs if r['severity'] == 'flag']
        self.assertEqual(len(flags), 2, [r['text'] for r in recs])
        self.assertTrue(any(t.startswith('Tmin/Tmax = 0.421 vs exp(−2 μ dmax) = 0.781') for t in flags), flags)   # analytical: a flag
        self.assertTrue(any('refines a twin (BASF 0.230) but the manuscript says' in t for t in flags), flags)
        recs = CA.check_refinement(self.st, [('p', 'The structure was refined as a two-component twin.')])
        self.assertFalse(any('BASF' in r['text'] for r in recs if r['severity'] == 'flag'))
        recs = CA.check_refinement(self.st, [('p', 'Nothing about it.')])
        self.assertTrue(any('does not mention twinning' in r['text'] for r in recs))


# a monoclinic P 1 21/c 1 cell (β = 100°) with a TWIN law in the .res, swapped per test
CIF_TWIN = """data_twin
_chemical_formula_sum 'Ca O'
_cell_length_a 10
_cell_length_b 8
_cell_length_c 12
_cell_angle_alpha 90
_cell_angle_beta 100
_cell_angle_gamma 90
_cell_formula_units_z 4
_space_group_name_H-M_alt 'P 1 21/c 1'
loop_
_space_group_symop_operation_xyz
'x, y, z'
'-x, y+1/2, -z+1/2'
'-x, -y, -z'
'x, -y+1/2, z+1/2'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
_atom_site_U_iso_or_equiv
Ca1 Ca 0.1 0.2 0.3 0.010
O1 O 0.3 0.1 0.2 0.015
_shelx_res_file
;
TITL twin
CELL 0.71073 10 8 12 90 100 90
ZERR 4 0 0 0 0 0 0
LATT 1
SYMM -X, 0.5+Y, 0.5-Z
SFAC CA O
UNIT 4 4
TWINLINE
BASF 0.30
CA1   1   0.100000  0.200000  0.300000  11.00000  0.01000
O1    2   0.300000  0.100000  0.200000  11.00000  0.01500
HKLF 4
END
;
"""


class TwinLaw(unittest.TestCase):
    def _st(self, twin):
        self.tmp = tempfile.mkdtemp(prefix='ciftwin_')
        path = os.path.join(self.tmp, 't.cif')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(CIF_TWIN.replace('TWINLINE', twin))
        return B.Structure(path)

    def tearDown(self):
        shutil.rmtree(getattr(self, 'tmp', ''), ignore_errors=True)

    @staticmethod
    def _twofold_about(st, v, direct=True):
        """The hkl matrix of a 180° rotation about a direct [uvw] (direct=True) or reciprocal (hkl)* direction."""
        Bd = B.cart_matrix(st); Bi = CA._inv3(Bd); Bs = CA._transpose(Bi); Bsi = CA._inv3(Bs)
        n = CA._mv(Bd, v) if direct else CA._mv(Bs, v)
        L = (sum(x * x for x in n)) ** 0.5; n = [x / L for x in n]
        R = [[2 * n[i] * n[j] - (1.0 if i == j else 0.0) for j in range(3)] for i in range(3)]
        return CA._mul(CA._mul(Bsi, R), Bs)

    def test_the_law_is_classified_in_the_cells_geometry(self):
        st = self._st('TWIN -1 0 0 0 -1 0 0 0 -1 2')
        tl = CA.twin_law(st, [[-1, 0, 0], [0, -1, 0], [0, 0, -1]])
        self.assertEqual((tl['kind'], tl['symop'], tl['centro']), ('inversion', '+', True))
        # a twofold about b (the monoclinic axis) is the space group's own operation
        tl = CA.twin_law(st, [[-1, 0, 0], [0, 1, 0], [0, 0, -1]])
        self.assertEqual((tl['kind'], tl['symop']), ('twofold', '+'))
        # a twofold about c*: exact in reciprocal space, irrational in direct space at β = 100°, and no symmetry operation
        Mcs = self._twofold_about(st, [0, 0, 1], direct=False)
        tl = CA.twin_law(st, Mcs)
        self.assertEqual((tl['kind'], tl['symop'], tl['exact'], tl['axis_recip']), ('twofold', None, 'reciprocal', [0, 0, 1]))
        self.assertFalse(tl['rational'])
        # a twofold about c (direct)
        tl = CA.twin_law(st, self._twofold_about(st, [0, 0, 1], direct=True))
        self.assertEqual((tl['kind'], tl['axis_direct'], tl['exact']), ('twofold', [0, 0, 1], 'direct'))
        self.assertEqual(CA.twin_law(st, [[1, 0, 0], [0, 1, 0], [0, 0, 1]])['kind'], 'identity')
        # a reticular law: h -> -h, k -> -k, l -> h/2 + l maps half the lattice points onto lattice points
        self.assertEqual(CA.twin_law(st, [[-1, 0, 0], [0, -1, 0], [0.5, 0, 1]])['index'], 2)

    def test_findings(self):
        # the inversion in a centrosymmetric structure: not a twin law at all
        recs = CA.check_twin(self._st('TWIN -1 0 0 0 -1 0 0 0 -1 2'), [('p', 'The structure was refined as an inversion twin.')])
        self.assertEqual([r['severity'] for r in recs], ['flag'], recs); self.assertIn('symmetry operation of the space group: not a twin law', recs[0]['text'])
        # the identity
        recs = CA.check_twin(self._st('TWIN 1 0 0 0 1 0 0 0 1 2'), None)
        self.assertIn('the identity', recs[0]['text']); self.assertEqual(recs[0]['severity'], 'flag')
        # a twofold about c* called an inversion twin in the text; the text's [001] axis is the reciprocal one
        st0 = self._st('TWIN -1 0 0 0 -1 0 0 0 -1 2'); Mcs = self._twofold_about(st0, [0, 0, 1], direct=False)
        st = self._st('TWIN ' + ' '.join('%.5f' % x for r in Mcs for x in r) + ' 2')
        recs = CA.check_twin(st, [('p', 'The crystal was refined as an inversion twin, twofold about [001].')])
        texts = [r['text'] for r in recs]
        self.assertTrue(any(r['severity'] == 'flag' and 'calls it an inversion twin, but' in r['text'] for r in recs), texts)
        self.assertTrue(any('about (001)*' in t for t in texts), texts)
        self.assertTrue(any('[001] is the reciprocal axis' in t for t in texts), texts)
        # the text's own matrix: the identity is a flag; 'related by inversion' counts as an inversion twin
        recs = CA.check_twin(self._st('TWIN -1 0 0 0 -1 0 0 0 -1 2'), [('p', 'Twinning is by reflection on (001), two-fold rotation about [001] or inversion. Twin matrix [1 0 0 / 0 1 0 / 0 0 1]. The two twin components are related by inversion.')])
        texts = [r['text'] for r in recs]
        self.assertTrue(any('the text prints, (1 0 0; 0 1 0; 0 0 1), is the identity' in t for t in texts), texts)
        self.assertFalse(any('describes a rotation or reflection twin' in t for t in texts), texts)
        self.assertEqual(CA.printed_twin_matrix('twin law ¯101,0¯10,00¯1 for the merohedral twin'), [[-1, 0, 1], [0, -1, 0], [0, 0, -1]])
        # a twin fraction that refined to nothing
        recs = CA.check_twin(self._st('TWIN -1 0 0 0 -1 0 0.41680 0 1 2\nBASF 0.004'), None)
        self.assertTrue(any('second component is absent' in r['text'] for r in recs), [r['text'] for r in recs])


class SiteFormula(unittest.TestCase):
    def test_sites_against_the_formula_sum_and_f000(self):
        tmp = tempfile.mkdtemp(prefix='cifsf_')
        try:
            path = os.path.join(tmp, 's.cif')
            with open(path, 'w', encoding='utf-8') as f:
                f.write(CIF)                                        # formula sum 'Mg O2 H2', F(000) 40; the sites hold Mg O2 H — one H short, 29 electrons
            st = B.Structure(path)
            self.assertEqual({k: round(v, 3) for k, v in CA.site_totals(st).items()}, {'Mg': 1.0, 'O': 2.0, 'H': 1.0})
            recs = CA.check_site_formula(st, [('p', 'The structural formula is Mg2O2H2.')])
            texts = [r['text'] for r in recs]
            self.assertEqual(recs, [], texts)                                                        # Mg and O agree; H is not judged
            recs = CA.check_site_formula(st, [('p', 'The structural formula, from the refined occupancies, is Mg2.00O2.00H2.00.')])
            texts = [r['text'] for r in recs]
            self.assertTrue(any("manuscript's structural formula" in t and 'Mg 1.00 from the sites vs 2 in the formula' in t for t in texts), texts)
            f = CA.check_f000(st)
            self.assertEqual(len(f), 1); self.assertIn('F(000) 40 in the .cif vs 29 electrons from the sites', f[0]['text'])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()

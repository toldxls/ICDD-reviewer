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


if __name__ == '__main__':
    unittest.main()

"""Tests de la logique de l'automate (sans Modbus).

Lancement : uv run python -m unittest discover -s tests
"""

import unittest

from tp_simu_auto.automate import Automate, Commandes, Defaut, Etape

DT = 0.1


def executer(automate: Automate, cmd: Commandes, duree_s: float) -> None:
    for _ in range(round(duree_s / DT)):
        automate.step(DT, cmd)


def impulsion(automate: Automate, **demandes: bool) -> None:
    automate.step(DT, Commandes(**demandes))


class TestCycleAutomatique(unittest.TestCase):
    def test_cycle_complet_puis_arret_en_fin_de_cycle(self):
        a = Automate()
        impulsion(a, depart_cycle=True)
        self.assertEqual(a.etape, Etape.SORTIE)
        self.assertTrue(a.y1)

        executer(a, Commandes(), 4.2)
        self.assertEqual(a.etape, Etape.TEMPO_HAUT)
        self.assertTrue(a.verin.b2_tige_sortie)
        self.assertFalse(a.y1 or a.y2)

        impulsion(a, arret_cycle=True)
        self.assertTrue(a.arret_fin_cycle)

        executer(a, Commandes(), 7.0)
        self.assertEqual(a.etape, Etape.REPOS)
        self.assertTrue(a.verin.b1_tige_rentree)
        self.assertEqual(a.cycles, 1)
        self.assertFalse(a.cycle_en_cours)
        self.assertAlmostEqual(a.duree_sortie_s, 4.0, delta=0.2)
        self.assertAlmostEqual(a.duree_rentree_s, 5.0, delta=0.2)

    def test_cycle_continu_sans_arret(self):
        a = Automate()
        impulsion(a, depart_cycle=True)
        executer(a, Commandes(), 25.0)
        self.assertGreaterEqual(a.cycles, 2)
        self.assertTrue(a.cycle_en_cours)

    def test_prise_d_origine_si_tige_sortie(self):
        a = Automate()
        a.verin.position_mm = 50.0
        impulsion(a, depart_cycle=True)
        self.assertEqual(a.etape, Etape.RENTREE)
        executer(a, Commandes(), 3.0)
        self.assertEqual(a.etape, Etape.SORTIE)
        self.assertEqual(a.cycles, 0)


class TestModeManuel(unittest.TestCase):
    def test_jog_deplace_et_arrete_la_tige(self):
        a = Automate()
        executer(a, Commandes(mode_manuel=True, jog_sortie=True), 1.0)
        self.assertEqual(a.etape, Etape.MANUEL)
        position = a.verin.position_mm
        self.assertAlmostEqual(position, 25.0, delta=3.0)

        executer(a, Commandes(mode_manuel=True), 1.0)
        self.assertEqual(a.verin.position_mm, position)

        executer(a, Commandes(mode_manuel=True, jog_rentree=True), 0.5)
        self.assertLess(a.verin.position_mm, position)

    def test_jog_s_arrete_en_fin_de_course(self):
        a = Automate()
        executer(a, Commandes(mode_manuel=True, jog_sortie=True), 6.0)
        self.assertTrue(a.verin.b2_tige_sortie)
        self.assertFalse(a.y1)
        self.assertEqual(a.defauts, Defaut.AUCUN)

    def test_commandes_contradictoires_sans_effet(self):
        a = Automate()
        executer(a, Commandes(mode_manuel=True, jog_sortie=True, jog_rentree=True), 1.0)
        self.assertFalse(a.y1 or a.y2)
        self.assertEqual(a.verin.position_mm, 0.0)

    def test_passage_en_manuel_interrompt_le_cycle(self):
        a = Automate()
        impulsion(a, depart_cycle=True)
        executer(a, Commandes(), 1.0)
        executer(a, Commandes(mode_manuel=True), 0.5)
        self.assertFalse(a.cycle_en_cours)
        self.assertFalse(a.y1 or a.y2)


class TestSecurites(unittest.TestCase):
    def test_arret_urgence_coupe_et_exige_deverrouillage(self):
        a = Automate()
        impulsion(a, depart_cycle=True)
        executer(a, Commandes(), 1.0)
        executer(a, Commandes(arret_urgence=True), 0.5)
        self.assertEqual(a.etape, Etape.DEFAUT)
        self.assertFalse(a.y1 or a.y2)
        self.assertFalse(a.cycle_en_cours)

        impulsion(a, arret_urgence=True, rearmement=True)
        self.assertIn(Defaut.ARRET_URGENCE, a.defauts)

        impulsion(a, rearmement=True)
        self.assertEqual(a.defauts, Defaut.AUCUN)
        self.assertEqual(a.etape, Etape.REPOS)

    def test_blocage_mecanique(self):
        a = Automate()
        a.verin.bloque = True
        impulsion(a, depart_cycle=True)
        executer(a, Commandes(), 1.5)
        self.assertIn(Defaut.BLOCAGE, a.defauts)
        self.assertFalse(a.y1)

    def test_pression_basse_declenche_timeout_sortie(self):
        a = Automate()
        a.verin.pression_basse = True
        impulsion(a, depart_cycle=True)
        executer(a, Commandes(), 9.0)
        self.assertIn(Defaut.TIMEOUT_SORTIE, a.defauts)
        self.assertNotIn(Defaut.BLOCAGE, a.defauts)

    def test_rearmement_puis_redemarrage(self):
        a = Automate()
        a.verin.bloque = True
        impulsion(a, depart_cycle=True)
        executer(a, Commandes(), 1.5)
        a.verin.bloque = False
        impulsion(a, rearmement=True)
        self.assertEqual(a.etape, Etape.REPOS)
        impulsion(a, depart_cycle=True)
        executer(a, Commandes(), 4.5)
        self.assertEqual(a.etape, Etape.TEMPO_HAUT)


if __name__ == "__main__":
    unittest.main()

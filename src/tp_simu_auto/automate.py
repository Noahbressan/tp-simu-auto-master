"""Automate simulé : un vérin pneumatique Festo et sa logique de commande.

La partie physique (``Verin``) est séparée de la partie commande
(``Automate``) pour pouvoir tester chacune sans le transport Modbus.
"""

from dataclasses import dataclass, field
from enum import IntEnum, IntFlag
from typing import ClassVar

from tp_simu_auto import modbus_map as mm


class Etape(IntEnum):
    """Étapes du Grafcet de l'automate (publiées dans IR_ETAPE)."""

    REPOS = mm.ETAPE_REPOS
    SORTIE = mm.ETAPE_SORTIE
    TEMPO_HAUT = mm.ETAPE_TEMPO_HAUT
    RENTREE = mm.ETAPE_RENTREE
    MANUEL = mm.ETAPE_MANUEL
    DEFAUT = mm.ETAPE_DEFAUT


class Defaut(IntFlag):
    """Défauts mémorisés jusqu'au réarmement (publiés dans IR_DEFAUTS)."""

    AUCUN = 0
    ARRET_URGENCE = mm.DEFAUT_ARRET_URGENCE
    TIMEOUT_SORTIE = mm.DEFAUT_TIMEOUT_SORTIE
    TIMEOUT_RENTREE = mm.DEFAUT_TIMEOUT_RENTREE
    BLOCAGE = mm.DEFAUT_BLOCAGE


@dataclass
class Verin:
    """Vérin double effet piloté par un distributeur 5/3 à centre fermé.

    - Y1 seule : la tige sort à ``vitesse_sortie_mm_s``.
    - Y2 seule : la tige rentre à ``vitesse_rentree_mm_s``.
    - Aucune bobine (ou les deux) : la tige reste immobile.
    """

    FACTEUR_PRESSION_BASSE: ClassVar[float] = 0.3

    position_mm: float = 0.0
    vitesse_sortie_mm_s: float = 25.0
    vitesse_rentree_mm_s: float = 20.0
    course_mm: float = 100.0

    # Défauts simulés, pilotés depuis l'IHM pour tester les alarmes
    bloque: bool = False
    pression_basse: bool = False

    @property
    def b1_tige_rentree(self) -> bool:
        return self.position_mm <= 0.0

    @property
    def b2_tige_sortie(self) -> bool:
        return self.position_mm >= self.course_mm

    def step(self, dt: float, y1: bool, y2: bool) -> None:
        """Avance la simulation de ``dt`` secondes."""
        if dt <= 0 or y1 == y2 or self.bloque:
            return
        facteur = self.FACTEUR_PRESSION_BASSE if self.pression_basse else 1.0
        if y1:
            self.position_mm = min(
                self.course_mm, self.position_mm + self.vitesse_sortie_mm_s * facteur * dt
            )
        else:
            self.position_mm = max(
                0.0, self.position_mm - self.vitesse_rentree_mm_s * facteur * dt
            )


@dataclass
class Commandes:
    """Image des coils écrits par l'IHM, lue à chaque cycle automate."""

    depart_cycle: bool = False
    arret_cycle: bool = False
    mode_manuel: bool = False
    jog_sortie: bool = False
    jog_rentree: bool = False
    arret_urgence: bool = False
    rearmement: bool = False


@dataclass
class Parametres:
    """Paramètres réglables depuis l'IHM (holding registers)."""

    tempo_haut_s: float = 1.0
    timeout_sortie_s: float = 8.0
    timeout_rentree_s: float = 10.0
    delai_blocage_s: float = 1.0


@dataclass
class Automate:
    """Logique de commande du vérin.

    Mode automatique (Grafcet) : REPOS -> SORTIE -> TEMPO_HAUT -> RENTREE,
    puis retour en SORTIE tant qu'aucun arrêt n'est demandé. Un arrêt
    demandé en cours de cycle est exécuté une fois la tige rentrée.

    Mode manuel : la tige se déplace tant que l'opérateur maintient la
    commande de sortie ou de rentrée, et s'arrête en fin de course.

    Sécurités : l'arrêt d'urgence et les défauts coupent les deux bobines.
    Les défauts restent mémorisés jusqu'au réarmement ; l'arrêt d'urgence ne
    peut être réarmé qu'une fois déverrouillé.
    """

    verin: Verin = field(default_factory=Verin)
    parametres: Parametres = field(default_factory=Parametres)

    etape: Etape = Etape.REPOS
    defauts: Defaut = Defaut.AUCUN
    y1: bool = False
    y2: bool = False
    cycle_en_cours: bool = False
    arret_fin_cycle: bool = False
    cycles: int = 0
    duree_sortie_s: float = 0.0
    duree_rentree_s: float = 0.0

    _temps_etape: float = 0.0
    _temps_sans_mouvement: float = 0.0
    _sortie_faite: bool = False

    def step(self, dt: float, cmd: Commandes) -> None:
        """Exécute un cycle automate de ``dt`` secondes."""
        self._temps_etape += dt

        if cmd.arret_urgence:
            self.defauts |= Defaut.ARRET_URGENCE
        if cmd.rearmement:
            self.defauts = Defaut.ARRET_URGENCE if cmd.arret_urgence else Defaut.AUCUN

        if self.defauts:
            if self.etape != Etape.DEFAUT:
                self._passer(Etape.DEFAUT)
            self.cycle_en_cours = False
            self.arret_fin_cycle = False
        elif cmd.mode_manuel:
            if self.etape != Etape.MANUEL:
                self._passer(Etape.MANUEL)
            self.cycle_en_cours = False
            self.arret_fin_cycle = False
        else:
            if self.etape in (Etape.MANUEL, Etape.DEFAUT):
                self._passer(Etape.REPOS)
            self._grafcet_auto(cmd)

        self._calculer_sorties(cmd)

        position_avant = self.verin.position_mm
        self.verin.step(dt, self.y1, self.y2)
        self._surveiller_mouvement(dt, position_avant)

    def _passer(self, etape: Etape) -> None:
        self.etape = etape
        self._temps_etape = 0.0

    def _grafcet_auto(self, cmd: Commandes) -> None:
        p = self.parametres
        if cmd.arret_cycle and self.cycle_en_cours:
            self.arret_fin_cycle = True

        if self.etape == Etape.REPOS:
            if cmd.depart_cycle:
                self.cycle_en_cours = True
                self.arret_fin_cycle = False
                self._sortie_faite = False
                # Prise d'origine : le cycle démarre tige rentrée
                self._passer(Etape.SORTIE if self.verin.b1_tige_rentree else Etape.RENTREE)

        elif self.etape == Etape.SORTIE:
            if self.verin.b2_tige_sortie:
                self.duree_sortie_s = self._temps_etape
                self._sortie_faite = True
                self._passer(Etape.TEMPO_HAUT)
            elif self._temps_etape > p.timeout_sortie_s:
                self.defauts |= Defaut.TIMEOUT_SORTIE

        elif self.etape == Etape.TEMPO_HAUT:
            if self._temps_etape >= p.tempo_haut_s:
                self._passer(Etape.RENTREE)

        elif self.etape == Etape.RENTREE:
            if self.verin.b1_tige_rentree:
                if self._sortie_faite:
                    self.duree_rentree_s = self._temps_etape
                    self.cycles += 1
                    self._sortie_faite = False
                if self.arret_fin_cycle:
                    self.cycle_en_cours = False
                    self.arret_fin_cycle = False
                    self._passer(Etape.REPOS)
                else:
                    self._passer(Etape.SORTIE)
            elif self._temps_etape > p.timeout_rentree_s:
                self.defauts |= Defaut.TIMEOUT_RENTREE

    def _calculer_sorties(self, cmd: Commandes) -> None:
        if self.defauts:
            self.y1 = self.y2 = False
        elif self.etape == Etape.SORTIE:
            self.y1, self.y2 = True, False
        elif self.etape == Etape.RENTREE:
            self.y1, self.y2 = False, True
        elif self.etape == Etape.MANUEL:
            # Commandes à action maintenue, verrouillées entre elles et en fin de course
            self.y1 = cmd.jog_sortie and not cmd.jog_rentree and not self.verin.b2_tige_sortie
            self.y2 = cmd.jog_rentree and not cmd.jog_sortie and not self.verin.b1_tige_rentree
        else:
            self.y1 = self.y2 = False

    def _surveiller_mouvement(self, dt: float, position_avant: float) -> None:
        """Détecte un vérin commandé qui ne bouge pas (blocage mécanique)."""
        commande = (self.y1 and position_avant < self.verin.course_mm) or (
            self.y2 and position_avant > 0.0
        )
        if commande and self.verin.position_mm == position_avant:
            self._temps_sans_mouvement += dt
            if self._temps_sans_mouvement >= self.parametres.delai_blocage_s:
                self.defauts |= Defaut.BLOCAGE
        else:
            self._temps_sans_mouvement = 0.0

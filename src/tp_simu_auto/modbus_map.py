"""Table d'échange Modbus de l'automate simulé.

Ce module est la seule source de vérité pour les adresses Modbus : il est
importé à la fois par le serveur (automate) et par les clients (IHM).
Aucune adresse ne doit être écrite en dur ailleurs.
"""

# Paramètres réseau
MODBUS_HOST = "127.0.0.1"
MODBUS_PORT = 502

# Identifiant d'esclave Modbus (unit id) de l'automate.
DEVICE_ID = 1

# --- Coils (lecture/écriture, FC1 / FC5) : demandes de l'IHM ---------------
# Les impulsions sont remises à 0 par l'automate dès qu'il les a prises en
# compte ; les commandes maintenues restent dans l'état écrit par l'IHM.
COIL_DEPART_CYCLE = 0  # impulsion : départ du cycle automatique
COIL_ARRET_CYCLE = 1  # impulsion : arrêt du cycle en fin de cycle
COIL_MODE_MANUEL = 2  # maintenu : 0 = automatique, 1 = manuel
COIL_JOG_SORTIE = 3  # maintenu : manuel, sortie de tige tant que 1
COIL_JOG_RENTREE = 4  # maintenu : manuel, rentrée de tige tant que 1
COIL_ARRET_URGENCE = 5  # maintenu : 1 = arrêt d'urgence enclenché
COIL_REARMEMENT = 6  # impulsion : réarmement des défauts
COIL_SIMU_BLOCAGE = 7  # maintenu : simulation d'un blocage mécanique
COIL_SIMU_PRESSION_BASSE = 8  # maintenu : simulation d'une pression d'air basse
NB_COILS = 9

COILS_IMPULSION = (COIL_DEPART_CYCLE, COIL_ARRET_CYCLE, COIL_REARMEMENT)

# --- Discrete inputs (lecture seule, FC2) : état de l'automate --------------
DI_Y1_SORTIE = 0  # bobine Y1 du distributeur 5/3 (sortie de tige)
DI_Y2_RENTREE = 1  # bobine Y2 du distributeur 5/3 (rentrée de tige)
DI_B1_TIGE_RENTREE = 2  # capteur de fin de course basse
DI_B2_TIGE_SORTIE = 3  # capteur de fin de course haute
DI_CYCLE_EN_COURS = 4
DI_DEFAUT = 5  # au moins un défaut actif
DI_ARRET_FIN_CYCLE = 6  # arrêt demandé, exécuté à la fin du cycle en cours
NB_DI = 7

# --- Input registers (lecture seule, FC4) -----------------------------------
IR_POSITION_TIGE = 0  # position de la tige, mm x POSITION_TIGE_SCALE
IR_ETAPE = 1  # étape active du Grafcet (voir ETAPE_*)
IR_DEFAUTS = 2  # mot de défauts (voir DEFAUT_*)
IR_CYCLES = 3  # nombre de cycles complets (modulo 65536)
IR_DUREE_SORTIE = 4  # durée de la dernière sortie, en 0,1 s
IR_DUREE_RENTREE = 5  # durée de la dernière rentrée, en 0,1 s
NB_IR = 6

# --- Holding registers (lecture/écriture, FC3 / FC6 / FC16) : paramètres ----
# Toutes les durées sont en 0,1 s.
HR_TEMPO_HAUT = 0  # temporisation en position haute pendant le cycle
HR_TIMEOUT_SORTIE = 1  # temps maximal pour atteindre B2
HR_TIMEOUT_RENTREE = 2  # temps maximal pour atteindre B1
NB_HR = 3

PARAMETRES_DEFAUT = {
    HR_TEMPO_HAUT: 10,
    HR_TIMEOUT_SORTIE: 80,
    HR_TIMEOUT_RENTREE: 100,
}

# --- Étapes du Grafcet (IR_ETAPE) -------------------------------------------
ETAPE_REPOS = 0
ETAPE_SORTIE = 1
ETAPE_TEMPO_HAUT = 2
ETAPE_RENTREE = 3
ETAPE_MANUEL = 4
ETAPE_DEFAUT = 5

# --- Bits du mot de défauts (IR_DEFAUTS) ------------------------------------
DEFAUT_ARRET_URGENCE = 1 << 0
DEFAUT_TIMEOUT_SORTIE = 1 << 1
DEFAUT_TIMEOUT_RENTREE = 1 << 2
DEFAUT_BLOCAGE = 1 << 3

# Facteur d'échelle : valeur registre = position en mm * POSITION_TIGE_SCALE.
# Avec 10, on transmet une résolution de 0,1 mm (100 mm -> 1000).
POSITION_TIGE_SCALE = 10


def position_mm_to_register(position_mm: float) -> int:
    """Convertit une position en mm en valeur de registre (uint16)."""
    return max(0, min(0xFFFF, round(position_mm * POSITION_TIGE_SCALE)))


def register_to_position_mm(value: int) -> float:
    """Convertit une valeur de registre en position en mm."""
    return value / POSITION_TIGE_SCALE


def secondes_to_register(secondes: float) -> int:
    """Convertit une durée en secondes en registre (0,1 s, uint16)."""
    return max(0, min(0xFFFF, round(secondes * 10)))


def register_to_secondes(value: int) -> float:
    """Convertit un registre en 0,1 s en secondes."""
    return value / 10

"""Client Modbus TCP de démonstration (test sans IHM).

Lance un cycle automatique, demande l'arrêt en fin de cycle puis suit le
retour au repos. Toutes les adresses viennent de ``tp_simu_auto.modbus_map``.

Usage : python client.py [port]   (port 502 par défaut)
"""

import sys
import time
from datetime import datetime

from pymodbus.client import ModbusTcpClient

from tp_simu_auto import modbus_map as mm

PERIODE_AFFICHAGE_S = 0.5
DUREE_MAX_S = 20.0

NOMS_ETAPES = {
    mm.ETAPE_REPOS: "REPOS",
    mm.ETAPE_SORTIE: "SORTIE",
    mm.ETAPE_TEMPO_HAUT: "TEMPO HAUT",
    mm.ETAPE_RENTREE: "RENTREE",
    mm.ETAPE_MANUEL: "MANUEL",
    mm.ETAPE_DEFAUT: "DEFAUT",
}


def horodatage() -> str:
    """Heure courante au format HH:MM:SS.mmm."""
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def ecrire_coil(client: ModbusTcpClient, adresse: int, valeur: bool, libelle: str) -> None:
    rep = client.write_coil(adresse, valeur, device_id=mm.DEVICE_ID)
    if rep.isError():
        raise RuntimeError(f"Ecriture du coil {adresse} refusee : {rep}")
    print(f"{horodatage()}  >>> {libelle}")


def lire_etat(client: ModbusTcpClient) -> list[int] | None:
    ir = client.read_input_registers(0, count=mm.NB_IR, device_id=mm.DEVICE_ID)
    if ir.isError():
        print(f"{horodatage()}  Erreur de lecture : {ir}")
        return None
    position = mm.register_to_position_mm(ir.registers[mm.IR_POSITION_TIGE])
    etape = NOMS_ETAPES.get(ir.registers[mm.IR_ETAPE], "?")
    print(
        f"{horodatage()}  etape={etape:<10} position={position:6.1f} mm"
        f"  cycles={ir.registers[mm.IR_CYCLES]}  defauts={ir.registers[mm.IR_DEFAUTS]:#06b}"
    )
    return ir.registers


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else mm.MODBUS_PORT
    client = ModbusTcpClient(mm.MODBUS_HOST, port=port)
    if not client.connect():
        print(f"Impossible de se connecter a {mm.MODBUS_HOST}:{port}")
        return 1
    try:
        print("--- Etat initial ---")
        lire_etat(client)
        ecrire_coil(client, mm.COIL_ARRET_URGENCE, False, "Arret d'urgence deverrouille")
        ecrire_coil(client, mm.COIL_MODE_MANUEL, False, "Mode automatique")
        ecrire_coil(client, mm.COIL_REARMEMENT, True, "Rearmement")
        time.sleep(0.5)

        print("--- Depart cycle ---")
        ecrire_coil(client, mm.COIL_DEPART_CYCLE, True, "Depart cycle")
        time.sleep(1.0)
        ecrire_coil(client, mm.COIL_ARRET_CYCLE, True, "Arret en fin de cycle")

        fin = time.monotonic() + DUREE_MAX_S
        while time.monotonic() < fin:
            time.sleep(PERIODE_AFFICHAGE_S)
            ir = lire_etat(client)
            if ir and ir[mm.IR_ETAPE] == mm.ETAPE_REPOS and ir[mm.IR_CYCLES] > 0:
                print("--- Cycle termine, verin au repos ---")
                return 0
        print("--- Le cycle ne s'est pas termine dans le temps imparti ---")
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())

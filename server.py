"""Serveur Modbus TCP simulant l'automate qui pilote le vérin Festo.

Toute l'interface avec l'extérieur passe par la table Modbus définie dans
``tp_simu_auto.modbus_map`` : à chaque cycle, les coils (demandes de l'IHM)
et les holding registers (paramètres) sont lus, la logique et la physique
sont exécutées, puis l'état est réécrit dans les discrete inputs et les
input registers.

Note pymodbus 3.15 : ModbusDeviceContext / ModbusSequentialDataBlock /
ModbusServerContext sont dépréciés au profit de SimData / SimDevice. On
construit donc un SimDevice et on garde une référence directe au
ModbusTcpServer, dont async_getValues / async_setValues donnent accès aux
registres depuis la boucle de simulation.

Usage : python server.py [port]   (port 502 par défaut)
"""

import asyncio
import sys
import time

from pymodbus.server import ModbusTcpServer
from pymodbus.simulator import DataType, SimData, SimDevice

from tp_simu_auto import modbus_map as mm
from tp_simu_auto.automate import Automate, Commandes, Defaut

# Codes fonction Modbus utilisés pour adresser la mémoire du serveur
FC_COILS = 1
FC_DISCRETE_INPUTS = 2
FC_HOLDING_REGISTERS = 3
FC_INPUT_REGISTERS = 4

PERIODE_CYCLE_S = 0.2
PERIODE_LOG_S = 1.0

NOMS_DEFAUTS = {
    Defaut.ARRET_URGENCE: "arret d'urgence",
    Defaut.TIMEOUT_SORTIE: "B2 non atteint (timeout sortie)",
    Defaut.TIMEOUT_RENTREE: "B1 non atteint (timeout rentree)",
    Defaut.BLOCAGE: "verin bloque",
}


def construire_device() -> SimDevice:
    """Construit la mémoire Modbus de l'automate (quatre blocs distincts)."""
    coils = [SimData(address=0, values=[False] * mm.NB_COILS, datatype=DataType.BITS)]
    discrete_inputs = [SimData(address=0, values=[False] * mm.NB_DI, datatype=DataType.BITS)]
    holding_registers = [
        SimData(
            address=0,
            values=[mm.PARAMETRES_DEFAUT[i] for i in range(mm.NB_HR)],
            datatype=DataType.UINT16,
        )
    ]
    input_registers = [SimData(address=0, values=[0] * mm.NB_IR, datatype=DataType.UINT16)]
    return SimDevice(
        id=mm.DEVICE_ID,
        simdata=(coils, discrete_inputs, holding_registers, input_registers),
    )


def lire_parametres(automate: Automate, hr: list[int]) -> None:
    """Applique les paramètres écrits par l'IHM (bornés à des valeurs sûres)."""
    p = automate.parametres
    p.tempo_haut_s = mm.register_to_secondes(hr[mm.HR_TEMPO_HAUT])
    p.timeout_sortie_s = max(1.0, mm.register_to_secondes(hr[mm.HR_TIMEOUT_SORTIE]))
    p.timeout_rentree_s = max(1.0, mm.register_to_secondes(hr[mm.HR_TIMEOUT_RENTREE]))


def decrire_defauts(defauts: Defaut) -> str:
    noms = [nom for bit, nom in NOMS_DEFAUTS.items() if bit in defauts]
    return ", ".join(noms) if noms else "aucun"


async def boucle_simulation(server: ModbusTcpServer, automate: Automate) -> None:
    """Cycle automate : lecture entrées -> logique et physique -> écriture sorties."""
    dernier_instant = time.monotonic()
    dernier_log = 0.0
    etape_prec = automate.etape
    defauts_prec = automate.defauts
    while True:
        await asyncio.sleep(PERIODE_CYCLE_S)
        maintenant = time.monotonic()
        dt = maintenant - dernier_instant
        dernier_instant = maintenant

        # 1. Lecture des demandes de l'IHM et des paramètres
        coils = [bool(c) for c in await server.async_getValues(mm.DEVICE_ID, FC_COILS, 0, count=mm.NB_COILS)]
        hr = await server.async_getValues(mm.DEVICE_ID, FC_HOLDING_REGISTERS, 0, count=mm.NB_HR)
        cmd = Commandes(
            depart_cycle=coils[mm.COIL_DEPART_CYCLE],
            arret_cycle=coils[mm.COIL_ARRET_CYCLE],
            mode_manuel=coils[mm.COIL_MODE_MANUEL],
            jog_sortie=coils[mm.COIL_JOG_SORTIE],
            jog_rentree=coils[mm.COIL_JOG_RENTREE],
            arret_urgence=coils[mm.COIL_ARRET_URGENCE],
            rearmement=coils[mm.COIL_REARMEMENT],
        )
        automate.verin.bloque = coils[mm.COIL_SIMU_BLOCAGE]
        automate.verin.pression_basse = coils[mm.COIL_SIMU_PRESSION_BASSE]
        lire_parametres(automate, hr)

        # 2. Logique et physique
        automate.step(dt, cmd)

        # 3. Acquittement des impulsions prises en compte
        for adresse in mm.COILS_IMPULSION:
            if coils[adresse]:
                await server.async_setValues(mm.DEVICE_ID, FC_COILS, adresse, [False])

        # 4. Publication de l'état
        verin = automate.verin
        di = [False] * mm.NB_DI
        di[mm.DI_Y1_SORTIE] = automate.y1
        di[mm.DI_Y2_RENTREE] = automate.y2
        di[mm.DI_B1_TIGE_RENTREE] = verin.b1_tige_rentree
        di[mm.DI_B2_TIGE_SORTIE] = verin.b2_tige_sortie
        di[mm.DI_CYCLE_EN_COURS] = automate.cycle_en_cours
        di[mm.DI_DEFAUT] = bool(automate.defauts)
        di[mm.DI_ARRET_FIN_CYCLE] = automate.arret_fin_cycle
        await server.async_setValues(mm.DEVICE_ID, FC_DISCRETE_INPUTS, 0, di)

        ir = [0] * mm.NB_IR
        ir[mm.IR_POSITION_TIGE] = mm.position_mm_to_register(verin.position_mm)
        ir[mm.IR_ETAPE] = int(automate.etape)
        ir[mm.IR_DEFAUTS] = int(automate.defauts)
        ir[mm.IR_CYCLES] = automate.cycles & 0xFFFF
        ir[mm.IR_DUREE_SORTIE] = mm.secondes_to_register(automate.duree_sortie_s)
        ir[mm.IR_DUREE_RENTREE] = mm.secondes_to_register(automate.duree_rentree_s)
        await server.async_setValues(mm.DEVICE_ID, FC_INPUT_REGISTERS, 0, ir)

        # 5. Traces console
        if automate.etape != etape_prec:
            print(f"[AUTOMATE] Etape {etape_prec.name} -> {automate.etape.name}")
            etape_prec = automate.etape
        if automate.defauts != defauts_prec:
            print(f"[AUTOMATE] Defauts : {decrire_defauts(automate.defauts)}")
            defauts_prec = automate.defauts
        if maintenant - dernier_log >= PERIODE_LOG_S:
            dernier_log = maintenant
            print(
                f"[AUTOMATE] etape={automate.etape.name:<10} Y1={int(automate.y1)} Y2={int(automate.y2)}"
                f" position={verin.position_mm:6.1f} mm cycles={automate.cycles}"
            )


async def main(port: int) -> None:
    automate = Automate()
    server = ModbusTcpServer(context=construire_device(), address=("0.0.0.0", port))
    tache = asyncio.create_task(boucle_simulation(server, automate))
    print(f"[AUTOMATE] Modbus TCP en ecoute sur le port {port} (Ctrl+C pour arreter)")
    try:
        await server.serve_forever()
    finally:
        tache.cancel()
        await server.shutdown()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else mm.MODBUS_PORT
    try:
        asyncio.run(main(port))
    except KeyboardInterrupt:
        pass
    print("[AUTOMATE] Arret.")

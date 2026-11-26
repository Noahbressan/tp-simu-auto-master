# IHM de supervision Node-RED — vérin VR-01

Ce dossier contient l'IHM de supervision du projet, exportée depuis Node-RED.

| Fichier      | Contenu                                                    |
|--------------|------------------------------------------------------------|
| `flows.json` | Flow complet de l'onglet « Supervision VR-01 » (20 nœuds)  |

## Modules Node-RED nécessaires

| Module                          | Version testée | Rôle                          |
|---------------------------------|----------------|-------------------------------|
| `node-red`                      | 5.0.10         | Environnement d'exécution     |
| `node-red-contrib-modbus`       | 5.62.1         | Client Modbus TCP             |
| `@flowfuse/node-red-dashboard`  | 1.37.0         | Dashboard 2.0 (écran)         |

Installation (une seule fois) :

```powershell
npm.cmd install -g --unsafe-perm node-red
cd $env:USERPROFILE\.node-red
npm.cmd install node-red-contrib-modbus @flowfuse/node-red-dashboard
```

## Mise en route

1. Lancer l'automate simulé (à la racine du projet) : `uv run python server.py`
2. Lancer Node-RED : `node-red.cmd`
3. Ouvrir http://localhost:1880, menu ☰ → **Import** → choisir `node-red/flows.json`
   → **Import** → **Deploy**.
4. Ouvrir l'écran : http://localhost:1880/dashboard/verin

## Contenu du flow

- **Lecture Modbus** (`modbus-read`) : coils, discrete inputs, input registers et
  holding registers de l'automate (127.0.0.1:502, esclave 1).
- **Modèle supervision** (`function`) : logique de l'IHM (états, alarmes,
  journal, tendance).
- **Écran de supervision** (`ui-template`) : synoptique, commandes, Grafcet,
  alarmes, mesures et réglages.
- **Écriture Modbus** (`modbus-flex-write`) : envoi des commandes de l'IHM vers
  l'automate.

Toutes les adresses utilisées sont décrites dans la table Modbus du
[README principal](../README.md).

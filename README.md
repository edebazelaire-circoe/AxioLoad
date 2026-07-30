# AxioLoad

## Version 0.10.0 — Optimisation totale chargement + tournées

L’onglet **1. Données** propose désormais une case **Optimisation totale**. Lorsqu’elle est activée, chaque ligne de marchandise reçoit un point d’enlèvement et un point de livraison, tandis que le lieu actuel du camion est renseigné au-dessus du tableau. Le calcul croise alors les tournées et la faisabilité physique du chargement.

Deux méthodes intégrées et gratuites sont comparées :

1. **ALNS couplé avec oracle de chargement LIFO** : l’ALNS déplace les clients entre les tournées et accepte une insertion uniquement si le moteur de rangement trouve un plan compatible avec les dimensions, le poids, les rotations, les essieux, les incompatibilités et l’ordre LIFO. Les résultats de faisabilité sont mis en cache.
2. **Co-évolution génétique bi-niveau 3L-CVRP** : le chromosome fait évoluer l’ordre des clients et le choix de l’heuristique de rangement. Un décodeur Split crée les tournées chargeables et compare les solutions selon trois priorités : nombre de véhicules, kilomètres, puis longueur occupée.

Le nouvel onglet **5. Optimisation totale** présente :

- les deux méthodes et leurs indicateurs ;
- le nombre de véhicules et la distance totale ;
- les tournées, les enlèvements et les livraisons ;
- le poids, les mètres linéaires et la méthode de chargement utilisée par véhicule ;
- le détail des placements ;
- la carte des tournées.

Cette évolution est isolée : lorsque la case n’est pas cochée, les optimisations de chargement et d’itinéraire fonctionnent exactement comme auparavant. Le calcul total n’ajoute pas d’entrée à l’historique de chargement classique.

### Limite de modélisation

L’architecture correspond au **3L-CVRP**, mais elle est adaptée au modèle actuel d’AxioLoad : les objets sont placés au plancher et la hauteur est contrôlée, sans gerbage automatique. Un gerbage industriel fiable nécessiterait des données supplémentaires de stabilité, de charge supportée et de compatibilité verticale.

## Version 0.9.0 — Carte et récapitulatif de tournée

L’onglet **4. Itinéraire** affiche désormais un fond de carte OpenStreetMap sous le tracé calculé. La carte reste une vue de consultation : zoom, déplacement et recentrage sont disponibles, sans outil de modification cartographique.

Nouveautés :

- fond de carte OpenStreetMap avec attribution ;
- couleur stable et distincte pour chaque client ;
- rappel de la couleur dans le tableau des missions, la carte, l’ordre de passage et le récapitulatif ;
- saisie du nombre d’unités et du type `palette`, `colis`, `unité` ou `unités mixtes` ;
- tableau récapitulatif sous la carte avec client, enlèvement, livraison, distance routière directe, quantité et poids ;
- totaux de la tournée : distance optimisée, unités transportées et poids total ;
- aucune modification des moteurs de chargement, de la vue 3D ou de l’historique des chargements.

Le fond de carte utilise les tuiles standard `tile.openstreetmap.org` uniquement pour l’affichage interactif courant. Pour un déploiement à forte fréquentation, il est recommandé de configurer un fournisseur de tuiles dédié ou une infrastructure cartographique interne.

AxioLoad est un logiciel d’optimisation de chargement pour palettes, colis et marchandises non gerbables. Le moteur recherche plusieurs plans à l’aide d’un portefeuille MaxRects et points extrêmes, minimise d’abord le nombre de véhicules puis la longueur réellement occupée, et contrôle la géométrie, les ouvertures, les obstacles, le poids, les essieux, le LIFO et les incompatibilités.

## Version 0.6.1

### Correctif 0.6.1

- correction de l’erreur JavaScript `ctx is not defined` ;
- rétablissement de l’affichage des solutions et de la vue 3D après optimisation ;
- test navigateur réel et test de non-régression dédiés au canvas.


- identité visuelle AxioLoad et palette inspirée de l’univers graphique de CIRCOE;
- logos Web en SVG et PNG, versions horizontale, compacte et icône/favicone;
- repère 3D unifié: longueur dans le sens longitudinal, largeur dans le sens transversal, hauteur verticale;
- références des marchandises affichées dans la scène;
- dimensions du véhicule et grille métrique intégrées au visuel;
- rotation et inclinaison de la vue par glisser, zoom à la molette;
- export PNG haute définition et PDF opérationnel intégrant la capture 3D;
- mètres linéaires calculés individuellement à partir de la longueur réellement occupée par chaque plan.

Le champ historique `linear_meter_width_mm` est conservé dans le catalogue pour préserver la compatibilité des données et des API. Il n’est plus utilisé pour la valeur affichée en « m.l. », conformément à la règle demandée dans cette version.

## Catalogue véhicules

L’onglet **0. Véhicules** permet de créer ou modifier:

- longueur, largeur et hauteur intérieures;
- largeur de référence historique LDM;
- charge utile;
- largeur et hauteur de l’ouverture arrière.

Chaque modification crée une nouvelle version et les calculs suivants utilisent immédiatement les dimensions enregistrées. Aucune clé API n’est requise pour l’interface locale.

## Démarrage local

```bash
python -m pip install -e '.[dev]' --no-build-isolation
pallet-optimizer --data-dir data serve --host 127.0.0.1 --port 8000
```

Ouvrir ensuite `http://127.0.0.1:8000`.

## Déploiement Docker

```bash
docker compose down
docker compose build --no-cache
docker compose up -d --force-recreate
```

Ne pas utiliser `docker compose down -v`, afin de conserver le volume de données.

## API facultative

Les clés API concernent uniquement l’intégration externe `POST /v1/optimizations`. L’interface, les véhicules, les imports, l’historique et les exports locaux n’en demandent aucune.

## Tests

```bash
pytest
PYTHONPATH=src python scripts/smoke_test.py
PYTHONPATH=src python scripts/ui_e2e.py
```

La recette couvre les moteurs d’optimisation, les dimensions véhicule, les cinq solutions, les mètres linéaires par plan, les imports CSV/XLSX, les exports, le PDF avec capture 3D, la navigation, l’affichage ordinateur/mobile, l’absence d’erreurs JavaScript et la persistance des données.

## Retour à la version précédente

Le ZIP complet de la version précédente est conservé dans `rollback/AxioLoad_0.9.0_original.zip`. Arrêtez Docker sans supprimer les volumes, restaurez cette archive puis reconstruisez l’image.

## Limites explicites

- aucun gerbage ni modification manuelle des placements dans la scène;
- modèle d’essieux simplifié à valider selon le véhicule réel;
- recherche heuristique déterministe, sans garantie d’optimalité mathématique;
- les versions historiques d’un véhicule sont référencées dans les résultats, mais le catalogue conserve uniquement sa dernière définition active.

# Rapport d’intervention — AxioLoad 0.8.0

## 1. Objet de la version

La version 0.8.0 ajoute un onglet autonome **« 4. Itinéraire »** permettant de préparer et comparer une tournée de camion à partir :

- d’un point de départ ;
- d’une liste de clients issue de l’onglet Données ou saisie manuellement ;
- d’un point d’enlèvement et d’un point de livraison par mission ;
- du poids associé à chaque mission ;
- de la capacité du camion ;
- d’une option de retour au point de départ.

L’onglet Itinéraire est isolé du moteur de chargement. Il ne modifie ni les palettes, ni les solutions 3D, ni les véhicules, ni l’historique des optimisations de chargement.

---

## 2. Analyse et adaptation des deux méthodes

### 2.1 HGS / PyVRP

PyVRP fournit un solveur de tournées performant, avec un cœur optimisé et une interface Python. La version 0.8.0 utilise PyVRP 0.13.x lorsqu’il est installé afin de produire une bonne graine d’ordre des missions.

Cette graine est ensuite adaptée au problème réel d’AxioLoad grâce à un **décodeur pickup-delivery** :

1. chaque mission est représentée par deux arrêts liés, un enlèvement et une livraison ;
2. le décodeur cherche séparément la meilleure position de l’enlèvement et de la livraison ;
3. l’enlèvement reste obligatoirement avant la livraison correspondante ;
4. la charge du camion est recalculée après chaque arrêt ;
5. la capacité saisie ne peut pas être dépassée ;
6. les ordres de missions sont croisés, mutés et améliorés par recherche locale.

Si PyVRP n’est pas disponible sur la machine, AxioLoad utilise un moteur HGS intégré comprenant :

- population diversifiée de permutations ;
- croisement ordonné ;
- mutations swap, inversion et déplacement ;
- conservation d’élites ;
- recherche locale ;
- cache des évaluations ;
- décodeur pickup-delivery identique.

### 2.2 ALNS

Le moteur ALNS a été intégré directement dans le projet pour éviter une dépendance supplémentaire.

Il utilise trois opérateurs de destruction :

- suppression aléatoire de missions ;
- suppression des missions présentant le coût marginal le plus élevé ;
- suppression de missions géographiquement proches.

Il utilise deux opérateurs de réparation :

- réinsertion gloutonne au meilleur coût ;
- réinsertion « regret » privilégiant les missions dont le report serait le plus pénalisant.

Les poids des opérateurs évoluent selon leurs performances. Une acceptation inspirée du recuit simulé permet de sortir des minima locaux. Les missions sont retirées et réinsérées sous forme de couples enlèvement-livraison, avec contrôle permanent de la précédence et de la capacité.

### 2.3 Comparabilité des résultats

Les deux méthodes utilisent exactement :

- les mêmes points géographiques ;
- la même matrice de distances ;
- la même matrice de durées ;
- la même capacité ;
- la même règle de retour ;
- le même budget de calcul sélectionné.

La comparaison des kilométrages est donc cohérente.

---

## 3. Calcul des distances et des tracés

### Mode connecté

- géocodage des adresses avec **Nominatim / OpenStreetMap** ;
- matrice routière avec le service **OSRM Table** ;
- tracé final avec le service **OSRM Route**.

### Mode de repli

Si OSRM est indisponible :

- calcul géodésique local ;
- coefficient routier de 1,28 ;
- durée estimée sur une vitesse moyenne de 50 km/h ;
- tracé direct entre les coordonnées ;
- avertissement visible dans les résultats.

Les champs acceptent également des coordonnées directes au format :

```text
49.4944, 0.1079
```

Cela permet de tester ou d’utiliser l’onglet sans service de géocodage.

---

## 4. Interface ajoutée

### Paramètres de tournée

- point de départ ;
- capacité du camion ;
- budget de calcul ;
- graine ;
- retour au point de départ.

### Tableau des missions

- client ;
- référence ;
- point d’enlèvement ;
- point de livraison ;
- poids ;
- statut de localisation ;
- suppression de ligne.

Le bouton **« Récupérer les clients saisis »** lit les lignes présentes dans l’onglet Données, regroupe les destinations identiques et additionne leurs poids.

### Résultats

Pour chaque méthode :

- nom du mode de calcul ;
- point d’interrogation avec définition ;
- distance totale ;
- durée estimée ;
- temps de calcul ;
- nombre d’itérations ;
- moteur réellement utilisé ;
- source des distances ;
- avertissements éventuels.

### Carte

La carte autonome affiche :

- le tracé routier ou le tracé de repli ;
- le départ et le retour ;
- les enlèvements ;
- les livraisons ;
- les numéros d’ordre ;
- les noms de clients ;
- le zoom ;
- le déplacement de la vue ;
- le recentrage.

Le panneau d’ordre de passage affiche également la charge restante après chaque arrêt.

---

## 5. Isolation du reste du logiciel

Aucune modification n’a été apportée :

- aux contrats du moteur de chargement ;
- aux règles des cinq méthodes de placement ;
- aux schémas SQLite ;
- aux données véhicules ;
- aux exports de chargement ;
- à l’historique de chargement ;
- aux règles de métrage linéaire ;
- à la vue 3D existante.

Les nouvelles routes HTTP sont isolées :

```text
GET  /api/route/geocode
POST /api/route/optimize
POST /api/route/compare
```

Un test vérifie qu’un calcul d’itinéraire ne crée aucune entrée dans l’historique des chargements.

---

## 6. Fichiers modifiés ou ajoutés

### Ajoutés

- `src/pallet_optimizer/route_optimization.py`
- `src/pallet_optimizer/static/route.js`
- `src/pallet_optimizer/static/route.css`
- `tests/test_route_optimization.py`

### Modifiés

- `src/pallet_optimizer/templates/index.html`
- `src/pallet_optimizer/api.py`
- `src/pallet_optimizer/engine.py`
- `src/pallet_optimizer/domain.py`
- `src/pallet_optimizer/__init__.py`
- `pyproject.toml`
- `Dockerfile`
- `.env.example`
- `README.md`

---

## 7. Tests réalisés

### Tests automatisés

- **54 tests réussis** ;
- précédence enlèvement avant livraison ;
- contrôle de capacité après chaque arrêt ;
- enlèvements multiples avant livraison lorsque la capacité le permet ;
- livraison forcée avant un nouvel enlèvement lorsque la capacité est insuffisante ;
- fonctionnement HGS ;
- fonctionnement ALNS ;
- comparaison des deux méthodes sur une matrice commune ;
- validation des coordonnées ;
- rejet d’une mission plus lourde que le camion ;
- absence d’impact sur l’historique des chargements ;
- présence des nouveaux fichiers dans le package.

### Test navigateur

- ouverture de l’onglet Itinéraire ;
- saisie de deux missions ;
- coordonnées manuelles ;
- comparaison HGS / ALNS ;
- deux cartes de résultat ;
- ordre des arrêts ;
- charge après chaque arrêt ;
- canvas de carte réellement dessiné ;
- aucune erreur JavaScript ou console.

Preuve : `reports/ui-route-e2e-v8.json`.

### Packaging

- wheel Python 0.8.0 construit ;
- module d’itinéraire inclus ;
- CSS et JavaScript inclus ;
- wheel réinstallé dans un emplacement propre ;
- import de `pallet_optimizer.route_optimization` validé.

---

## 8. Limites et précautions

### Services publics

Les services publics Nominatim et OSRM sont adaptés à des essais et à un usage modéré. Pour un usage intensif ou un grand nombre de points, il faut configurer des instances internes avec :

```text
AXIOLOAD_OSRM_URL
AXIOLOAD_NOMINATIM_URL
```

La matrice publique est volontairement limitée à 80 points physiques dans cette version.

### PyVRP

PyVRP n’était pas disponible sur l’index Python fermé de l’environnement de recette. Le branchement PyVRP a été codé selon son API documentée et le Dockerfile demande l’option `routing`, mais le test d’exécution effectué ici a utilisé le moteur HGS intégré de repli.

### Docker

Docker n’est pas installé dans l’environnement de recette. Le Dockerfile a été mis à jour pour installer :

```text
.[solver,routing]
```

La construction finale de l’image devra donc être confirmée sur la machine de déploiement.

### Persistance

Les itinéraires calculés ne sont pas ajoutés à l’historique de chargement, afin de conserver l’isolation demandée. Une persistance dédiée des tournées pourra être ajoutée dans une version ultérieure.

---

## 9. Retour à la version précédente

Le fichier suivant est inclus dans le ZIP :

```text
rollback/AxioLoad_0.7.0_original.zip
```

Pour revenir à la version précédente avec Docker :

```powershell
docker compose down
# Restaurer les fichiers de la version 0.7.0
docker compose build --no-cache
docker compose up -d --force-recreate
```

Ne pas utiliser `docker compose down -v`, afin de ne pas supprimer les données persistantes.

---

## 10. Sources techniques étudiées

- PyVRP documentation : https://pyvrp.readthedocs.io/en/stable/
- PyVRP paper : https://arxiv.org/abs/2403.13795
- ALNS documentation : https://alns.readthedocs.io/en/latest/
- OSRM API : https://project-osrm.org/docs/v5.23.0/api/

# AxioLoad 0.10.0 — Rapport d’intervention

## 1. Objet de la version

La version 0.10.0 ajoute un mode **Optimisation totale** permettant de croiser dans un même calcul :

- le nombre de véhicules nécessaires ;
- la composition des tournées ;
- les kilomètres parcourus ;
- la faisabilité physique du chargement ;
- la rotation autorisée ou interdite des marchandises ;
- l’ordre de déchargement LIFO ;
- la longueur réellement occupée dans chaque véhicule.

Cette évolution est isolée du fonctionnement existant. Lorsque la case **Optimisation totale** n’est pas cochée, les onglets Chargement, Résultats, Historique et Itinéraire conservent leur comportement antérieur.

## 2. Nouvelles fonctions d’interface

### Onglet 1 — Données

Ajout d’une case **Optimisation totale**.

Lorsqu’elle est activée :

- un champ permet de renseigner le lieu actuel du camion ;
- le retour au lieu de départ peut être activé ou désactivé ;
- les enlèvements vides peuvent être remplis avec le lieu de départ ;
- chaque ligne de marchandise affiche :
  - le point d’enlèvement ;
  - le point de livraison ;
  - l’état de localisation des deux adresses ;
- les adresses peuvent être géocodées individuellement ou en une seule opération.

Les clients déjà présents dans le tableau de marchandises sont directement réutilisés. Plusieurs références portant le même client et les mêmes lieux sont regroupées dans la même demande client par le moteur intégré.

### Onglet 5 — Optimisation totale

Création d’un nouvel onglet récapitulatif présentant :

- les deux méthodes comparées ;
- le nombre de véhicules ;
- la distance totale ;
- la durée estimée ;
- le poids total ;
- le nombre d’unités ;
- les mètres linéaires cumulés ;
- la carte des tournées ;
- l’ordre des enlèvements ;
- l’ordre des livraisons ;
- le détail de chaque véhicule ;
- la méthode de rangement retenue par l’oracle ;
- le plan de placement détaillé ;
- le nombre d’appels et de réutilisations du cache de faisabilité.

## 3. Méthodes intégrées

### 3.1 ALNS couplé avec oracle de chargement LIFO

Le moteur ALNS modifie la composition des tournées avec plusieurs opérateurs de destruction et de réparation.

Chaque insertion de client est soumise à un oracle de chargement qui :

- récupère toutes les marchandises associées aux clients de la tournée ;
- recalcule leur ordre de déchargement ;
- teste plusieurs méthodes rapides de rangement ;
- contrôle les dimensions du véhicule et de son ouverture ;
- applique les rotations autorisées ;
- contrôle le poids, les essieux, les obstacles et les incompatibilités ;
- rejette la tournée si aucun plan LIFO valide n’est trouvé.

Un cache mémorise les combinaisons déjà contrôlées afin de ne pas recalculer inutilement leur faisabilité.

### 3.2 Co-évolution génétique bi-niveau 3L-CVRP

Le chromosome génétique contient :

- l’ordre des clients ;
- la méthode de rangement à utiliser.

Un décodeur de type **Split** découpe le parcours en plusieurs tournées. Chaque segment proposé doit être validé par l’oracle de chargement.

Les mutations portent sur :

- les permutations de clients ;
- les inversions de séquences ;
- les déplacements de clients ;
- le choix du moteur de rangement.

## 4. Fonction objectif

Les solutions sont comparées de manière lexicographique :

1. réduire le nombre de véhicules ;
2. réduire la distance totale ;
3. réduire la longueur occupée cumulée.

Cela évite qu’une légère économie kilométrique conduise artificiellement à utiliser un véhicule supplémentaire.

## 5. Règles métier conservées

Le calcul intégré réutilise les données et contrôles déjà présents dans AxioLoad :

- dimensions des marchandises ;
- dimensions intérieures du véhicule ;
- ouverture arrière ;
- poids et charge utile ;
- limites d’essieux ;
- obstacles ;
- marge de sécurité ;
- écart spécifique ;
- rotation autorisée ou interdite ;
- groupes et incompatibilités ;
- contrainte LIFO.

Aucun schéma de base de données existant n’a été modifié.

Aucune route API existante n’a été modifiée. Une nouvelle route isolée a été ajoutée :

```text
POST /api/total/optimize
```

Le calcul total n’ajoute pas d’entrée dans l’historique classique des optimisations de chargement.

## 6. Modèle des enlèvements et livraisons

Pour conserver un plan de chargement statique cohérent et contrôlable, chaque tournée intégrée suit le modèle suivant :

1. départ depuis la position actuelle du camion ;
2. enlèvements dans l’ordre inverse des livraisons ;
3. livraisons selon l’ordre LIFO ;
4. retour facultatif au point de départ.

Cette règle garantit que les marchandises du premier client livré restent accessibles sans déplacer les marchandises des clients suivants.

## 7. Limite de modélisation

La solution constitue une adaptation du **3L-CVRP** au modèle actuel d’AxioLoad.

Les objets restent placés au plancher. La hauteur est contrôlée, mais aucun gerbage automatique n’est effectué. L’ajout d’un gerbage fiable nécessiterait notamment :

- une capacité de charge supportée par objet ;
- des règles de stabilité ;
- des contraintes de compatibilité verticale ;
- des données sur le centre de gravité et la surface réellement porteuse.

La version est limitée à 35 lignes clients et conserve la limite existante sur le nombre d’objets développés.

## 8. Distances et géocodage

Le mode total réutilise les services déjà présents dans l’onglet Itinéraire :

- géocodage des adresses ;
- matrice routière OSRM / OpenStreetMap ;
- géométrie du tracé.

Si OSRM est indisponible, le mécanisme local existant fournit une estimation géodésique avec coefficient routier et affiche un avertissement.

## 9. Fichiers ajoutés

- `src/pallet_optimizer/total_optimization.py`
- `src/pallet_optimizer/static/total.js`
- `src/pallet_optimizer/static/total.css`
- `tests/test_total_optimization.py`

## 10. Fichiers modifiés

- `src/pallet_optimizer/api.py`
- `src/pallet_optimizer/templates/index.html`
- `src/pallet_optimizer/static/app.js`
- `src/pallet_optimizer/engine.py`
- `src/pallet_optimizer/domain.py`
- `src/pallet_optimizer/route_optimization.py`
- `src/pallet_optimizer/__init__.py`
- `pyproject.toml`
- `README.md`

Les changements apportés aux fichiers de version ne modifient pas la logique des moteurs existants.

## 11. Tests réalisés

- 58 tests automatisés réussis ;
- validation des deux méthodes intégrées ;
- contrôle d’une marchandise ne pouvant entrer qu’après rotation à 90° ;
- contrôle de la présence de chaque client une seule fois ;
- contrôle du nombre maximal de véhicules ;
- contrôle de la présence d’un plan de chargement sur chaque tournée ;
- contrôle que le calcul total ne modifie pas l’historique classique ;
- test de non-régression de l’optimisation classique ;
- vérification syntaxique de `app.js`, `route.js` et `total.js` ;
- test navigateur de la case, de la saisie des coordonnées, du calcul et de l’onglet 5 ;
- absence d’erreur JavaScript pendant le scénario navigateur ;
- smoke test du moteur classique.

## 12. Retour à la version précédente

Le fichier suivant est inclus dans le dossier `rollback` :

```text
rollback/AxioLoad_0.9.0_original.zip
```

Procédure Docker :

```powershell
docker compose down
```

Extraire ensuite la version 0.9.0 à la place de la version 0.10.0, puis exécuter :

```powershell
docker compose build --no-cache
docker compose up -d --force-recreate
```

Ne pas utiliser :

```powershell
docker compose down -v
```

Cette option supprimerait les volumes de données.

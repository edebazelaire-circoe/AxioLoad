# Rapport d’intervention - AxioLoad 0.4.0

## Objet

Cette version part de Pallet Loading Optimizer V3 et applique uniquement les évolutions demandées: identité AxioLoad, palette visuelle cohérente avec l’univers CIRCOE, correction et enrichissement de la vue 3D, export opérationnel avec image, et calcul individualisé des mètres linéaires.

Un point de restauration complet a été créé avant modification dans:

`rollback/pallet_loading_optimizer_v3_original.zip`

## Fonctionnalités ajoutées ou corrigées

### Identité et interface

- remplacement du nom visible par **AxioLoad**;
- intégration du concept C validé;
- palette bleu nuit, bleu logistique, cyan, turquoise, menthe et accent corail;
- contrastes renforcés sur les textes, boutons, tableaux, messages et états actifs;
- adaptation ordinateur et mobile;
- favicon et métadonnées de thème.

### Logos livrés

Ressources transparentes dans `src/pallet_optimizer/static/brand/`:

- horizontal fond clair: SVG et PNG 2048 px;
- horizontal fond sombre: SVG et PNG 2048 px;
- compact: SVG et PNG 1400 px;
- icône: SVG et PNG 1024 px;
- favicon: SVG, ICO et PNG 32, 192 et 512 px.

### Système de coordonnées 3D

La base de données et l’API n’ont pas été modifiées. La conversion est réalisée uniquement dans le visualiseur:

- donnée `y_mm` -> longueur longitudinale du camion;
- donnée `x_mm` -> largeur transversale du camion;
- donnée `z_mm` -> hauteur verticale.

Les marchandises, obstacles, dimensions et inspections utilisent ce même repère.

### Vue 3D

- références affichées au-dessus de chaque marchandise, en surimpression pour éviter qu’une face dessinée ensuite ne les masque;
- dimensions longueur, largeur et hauteur autour du véhicule;
- grille au sol tous les mètres, avec repères renforcés tous les cinq mètres;
- indication de la porte arrière;
- rotation horizontale, inclinaison verticale et zoom;
- textes dessinés en espace écran pour rester droits et lisibles pendant les mouvements;
- métriques du plan courant affichées directement dans la scène.

### Export opérationnel

- nouveau bouton **PDF opérationnel avec vue 3D**;
- capture PNG haute définition 1800 x 1100 de la scène courante;
- intégration de la capture dans un PDF AxioLoad;
- synthèse de la solution, dimensions du véhicule, longueur occupée et mètres linéaires;
- tableau opérationnel avec référence, destination, position longitudinale/transversale, dimensions et orientation;
- contrôle serveur empêchant l’export si les métriques affichées diffèrent du plan enregistré;
- export PNG haute définition séparé;
- exports CSV, XLSX et JSON conservés.

### Mètres linéaires

Avant correction, la valeur provenait de la surface totale divisée par une largeur de référence. Elle restait donc identique pour des dispositions différentes contenant les mêmes marchandises.

La règle appliquée en 0.4.0 est désormais:

`max(y_mm + envelope_length_mm) / 1000`

Cette valeur est calculée pour chaque plan véhicule. Pour une solution multi-véhicules, le total est la somme des longueurs occupées de chacun des véhicules.

Les champs historiques `linear_meters`, `total_linear_meters` et `linear_meter_width_mm` sont conservés pour ne pas casser les données, les exports ou les intégrations existantes. `linear_meter_width_mm` reste modifiable mais n’intervient plus dans la valeur m.l. affichée.

## Fichiers modifiés

- `README.md`
- `pyproject.toml`
- `scripts/ui_e2e.py`
- `src/pallet_optimizer/__init__.py`
- `src/pallet_optimizer/api.py`
- `src/pallet_optimizer/domain.py`
- `src/pallet_optimizer/engine.py`
- `src/pallet_optimizer/exports.py`
- `src/pallet_optimizer/static/app.css`
- `src/pallet_optimizer/static/app.js`
- `src/pallet_optimizer/templates/index.html`
- `tests/test_architecture_persistence_api.py`
- `tests/test_engine.py`

## Fichiers ajoutés

- `src/pallet_optimizer/metrics.py`
- `docs/brand-guidelines.md`
- toutes les ressources de `src/pallet_optimizer/static/brand/`
- rapports et captures V4 dans `reports/`
- point de restauration dans `rollback/`

## Éléments volontairement non modifiés

- structure SQLite;
- tables, colonnes et migrations;
- format des véhicules;
- contrats existants de l’API publique;
- règles de géométrie, poids, essieux, LIFO, compatibilité et séparation;
- portefeuille et ordre des moteurs d’optimisation;
- dépendances Python;
- mécanisme d’isolation des entreprises;
- imports CSV/XLSX existants.

La seule route ajoutée est:

`POST /api/history/{run_id}/export-operational.pdf`

Elle complète les routes existantes sans les remplacer.

## Tests réalisés

### Automatisation

- 40 tests Pytest réussis;
- calcul individualisé des mètres linéaires sur deux dispositions distinctes;
- présence de solutions avec 1,80 m, 2,20 m et 3,20 m pour un même ensemble de marchandises selon la disposition;
- cohérence `linear_meters == occupied_length_m` pour chaque plan;
- contrôle de cohérence entre métriques affichées et export;
- génération du PDF opérationnel avec capture PNG;
- rejet d’un export comportant une métrique falsifiée;
- imports CSV et XLSX;
- exports CSV, XLSX et JSON;
- catalogue véhicules sans clé API;
- moteurs, géométrie, LIFO, essieux, multi-véhicules et 100 objets;
- isolation et sauvegarde/restauration des bases.

### Interface

- scénario navigateur complet sur ordinateur;
- modification d’un véhicule en 5 000 x 1 600 x 2 700 mm;
- calcul de trois palettes de 1 200 x 800 mm;
- vérification d’un résultat de 2,40 m occupés et 2,40 m.l.;
- rendu de la scène, grille, références et dimensions;
- téléchargement réel du PDF opérationnel;
- navigation mobile en 390 x 844 px;
- absence d’erreurs JavaScript et d’erreurs console pendant le scénario;
- absence de débordement global de la page mobile.

### Paquet et données

- syntaxe JavaScript validée par Node;
- compilation Python complète;
- smoke test réussi;
- roue Python 0.4.0 construite puis installée dans un répertoire propre;
- présence de tous les logos dans la roue;
- ouverture d’une copie des bases SQLite V3 sans migration ni perte des deux véhicules;
- PDF rendu en image puis contrôlé visuellement.

Les preuves se trouvent dans `reports/`.

## Risques et limites

- Docker n’est pas installé dans l’environnement de recette. Le Dockerfile et Compose n’ont pas été modifiés, mais la construction de l’image doit être confirmée sur la machine de déploiement.
- Pour une solution utilisant plusieurs véhicules, le PDF contient la capture 3D du véhicule actuellement sélectionné et le tableau de tous les véhicules.
- Comme en V3, le catalogue ne conserve que la dernière définition active d’un modèle. Lors de l’ouverture d’un calcul très ancien après modification du véhicule, la scène peut utiliser la définition active comme solution de repli si la version exacte n’est plus disponible dans le catalogue.
- Le logiciel reste un solveur heuristique, sans garantie d’optimalité mathématique.

## Retour à la V3

### Avec Docker

1. Sauvegarder le volume de données actuel.
2. Arrêter l’application sans supprimer le volume:

```powershell
docker compose down
```

3. Extraire `rollback/pallet_loading_optimizer_v3_original.zip` dans un dossier propre.
4. Reprendre le même volume de données dans le fichier Compose.
5. Reconstruire et redémarrer:

```powershell
docker compose build --no-cache
docker compose up -d --force-recreate
```

Ne pas utiliser `docker compose down -v`.

### Sans Docker

1. Arrêter le serveur AxioLoad.
2. Conserver le dossier de données actuel.
3. Extraire la V3 depuis le ZIP de restauration.
4. Redémarrer la V3 en pointant vers le même dossier de données.

Aucune migration de base n’ayant été ajoutée, le retour à la V3 ne nécessite pas de conversion de données.

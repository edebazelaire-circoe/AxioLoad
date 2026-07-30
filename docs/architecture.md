# Architecture implémentée

## Modules

- `domain.py`: contrats immuables, véhicules versionnés et diagnostics structurés.
- `normalization.py`: contrat unique pour JSON, CSV et XLSX, avec catalogue véhicule injecté par entreprise.
- `envelopes.py`, `validation.py`: enveloppes physiques et contrôles de faisabilité purs.
- `packing.py`: portefeuille MaxRects et points extrêmes, rotations, contraintes de placement et partitionnement multi-véhicules.
- `ranking.py`, `engine.py`: recherche bornée, validation finale, classement et diversité.
- `service.py`: frontière applicative, statuts de calcul et injection du catalogue tenant.
- `persistence.py`: registre central minimal, une base SQLite par entreprise, historique et catalogue véhicules persistant.
- `api.py`: application web, catalogue véhicules, imports, historique, exports et API publique.
- `exports.py`: PDF, XLSX, CSV et JSON. Le PNG est produit par le Canvas à partir des placements validés.

## Invariants

Le moteur ne dépend ni de FastAPI, ni de SQLite, ni du rendu. Tous les canaux construisent un `OptimizationProblem`. La scène 3D lit directement les `Placement` retournés. La meilleure solution est stable sous graine fixe.

Aucun plan n’est classé avant validation de la géométrie, de l’ouverture, du poids, des essieux, du LIFO et des compatibilités.

## Coordonnées

- `x`: largeur depuis le côté gauche;
- `y`: profondeur depuis la porte arrière, située à `y=0`;
- `z`: hauteur, obligatoirement `0` pour les objets non gerbés;
- un ordre de livraison élevé signifie un déchargement plus tôt.

## Catalogue véhicules

Chaque entreprise possède sa propre table `vehicle_models`. Un véhicule est identifié par `model_id`; toute modification réelle incrémente `version`. Un résultat conserve `model_id@version`, ce qui garantit la traçabilité des dimensions utilisées.

L’écran 0 permet de modifier les dimensions intérieures, l’ouverture, la charge utile et la largeur de référence LDM. Le moteur relit le catalogue persistant à chaque calcul.

## Recherche

Le moteur exécute un portefeuille de huit stratégies:

- quatre variantes MaxRects: short-side, area-fit, bottom-left et balanced;
- quatre variantes à points extrêmes: front-left, front-right, narrow-lanes et depth-columns.

Chaque méthode est combinée à plusieurs ordres déterministes et variantes de partitionnement. Les plans sont classés d’abord par nombre de véhicules, puis par longueur réellement occupée, métrage linéaire, charge d’essieux et équilibre transversal.

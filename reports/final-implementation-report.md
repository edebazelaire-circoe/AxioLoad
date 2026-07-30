# Rapport de correction et recette V2

## Verdict

**Correction acceptée.** Le cas remonté dans l’interface, trois palettes de 1200 × 800 × 1200 mm et 500 kg dans une semi-remorque, produit désormais des plans de rangement valides. Le meilleur plan utilise une profondeur de 1,20 m dans le véhicule standard de 2 450 mm de largeur intérieure.

## Corrections principales

### Moteur de rangement

Le moteur ne repose plus uniquement sur quelques points candidats. Il exécute un portefeuille de méthodes:

- MaxRects Best Short Side Fit;
- MaxRects Best Area Fit;
- MaxRects Bottom-Left;
- MaxRects équilibré;
- points extrêmes front-left, front-right, narrow-lanes et depth-columns;
- multi-départs déterministes et rotations 0°/90°;
- partitionnement multi-véhicules.

Chaque plan est revalidé avant affichage: limites du véhicule, ouverture arrière, collisions, obstacles, hauteur, poids, essieux, LIFO et compatibilités.

### Écran 0 Véhicules

Un nouvel écran **0. Véhicules** permet de créer, modifier, supprimer ou restaurer les modèles de véhicules. Les champs modifiables sont:

- longueur, largeur et hauteur intérieures;
- largeur de référence LDM;
- charge utile;
- largeur et hauteur d’ouverture.

Les données sont persistées dans la base SQLite de l’entreprise. Une modification réelle crée une nouvelle version et le résultat conserve l’identifiant `model_id@version` utilisé.

### Diagnostics

La ligne générique « Aucune solution réalisable » a été supprimée. Lorsqu’un cas est réellement impossible, l’interface affiche une cause précise, par exemple un objet trop long, trop large, trop haut, trop lourd ou une surface totale insuffisante.

## Critères d’acceptation vérifiés

| Critère | Résultat |
|---|---|
| Une palette standard produit un plan | Validé |
| Trois palettes 1200 × 800 produisent un plan | Validé, 3 placements |
| Les palettes ne dépassent pas les dimensions intérieures | Validé par tests géométriques |
| Une largeur véhicule modifiée change le rangement | Validé: profondeur de 1,20 m à 2 450 mm de large, puis 2,40 m à 1 600 mm |
| Une dimension trop petite est refusée explicitement | Validé avec `ITEM_DOES_NOT_FIT` |
| Les dimensions modifiées sont persistées | Validé par API et test E2E |
| L’écran 0 est présent et utilisable | Validé par navigateur headless |
| Le calcul affiche au moins une solution lorsqu’elle existe | Validé |
| Le visualiseur 3D utilise le véhicule versionné | Validé |

## Recette automatisée

- **33 tests Pytest passent**.
- Compilation de tous les modules Python: OK.
- Syntaxe JavaScript: OK.
- Smoke test API complet: statut `completed`.
- Construction et installation de la roue Python `0.2.0`: OK; test du paquet installé avec trois palettes: 3 placements, 1,20 m occupé.
- Test E2E navigateur: modification d’une semi-remorque à 1 600 mm de largeur, saisie de trois palettes, calcul, résultat à 2,40 m de profondeur et Canvas visible.
- Benchmark 100 objets sous budget d’une seconde: 100 placements retournés, statut `completed_with_time_limit`.

## Fichiers de preuve

- `reports/test-results-v2.txt`
- `reports/acceptance-cases-v2.txt`
- `reports/benchmark-100-items-v2.txt`
- `reports/ui-results-v2.png`
- `reports/vehicle-screen-v2.png`
- `dist/pallet_loading_optimizer-0.2.0-py3-none-any.whl`
- `docs/optimization-methods.md`

## Limites conservées

Le moteur est un solveur heuristique borné. Il cherche de bons plans et élimine les plans invalides, mais ne revendique pas une preuve d’optimalité globale. Le gerbage et la simulation détaillée de manutention restent hors périmètre.

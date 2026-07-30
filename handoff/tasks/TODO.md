# TODO — Pallet Loading Optimizer

## Mode opératoire

Commencer impérativement par la tâche 00. L’orchestrateur pilote la suite, vérifie les preuves et adapte les tâches si nécessaire. Une seule tâche doit être active à la fois.

## Règles globales

- Les agents de code doivent charger `/caveman` et `/coding-guideline` depuis `~/ai/skills/`.
- Ne jamais sacrifier une contrainte dure pour améliorer un score.
- Aucun calcul 3D ou export ne doit réinterpréter la physique.
- Toute modification du contrat public exige tests de contrat et mise à jour documentaire.
- Chaque tâche doit produire un court rapport dans ses Handoff Notes ou un fichier de rapport associé.

## Ordre des tâches

- [x] 00 — [Orchestration du projet](00-orchestrator/TASK.md)
- [x] 01 — [Contrats métier et unités](01-domain-contracts/TASK.md)
- [x] 02 — [Portes d’architecture](02-architecture-gates/TASK.md)
- [x] 03 — [Normalisation des entrées](03-problem-normalization/TASK.md)
- [x] 04 — [Modèle véhicule versionné](04-vehicle-model/TASK.md)
- [x] 05 — [Formes et enveloppes de sécurité](05-cargo-envelope/TASK.md)
- [x] 06 — [Validation géométrique](06-feasibility-geometry/TASK.md)
- [x] 07 — [Rotation et placements candidats](07-rotation-and-placement/TASK.md)
- [x] 08 — [Poids, centre de gravité et essieux](08-weight-axles/TASK.md)
- [x] 09 — [Ordre de livraison et accessibilité](09-delivery-access/TASK.md)
- [x] 10 — [Compatibilités et groupes](10-compatibility-groups/TASK.md)
- [x] 11 — [Heuristiques véhicule unique](11-single-vehicle-heuristics/TASK.md)
- [x] 12 — [Amélioration sous budget temps](12-local-search/TASK.md)
- [x] 13 — [Optimisation multi-véhicules](13-multi-vehicle/TASK.md)
- [x] 14 — [Classement et cinq solutions distinctes](14-ranking-diversity/TASK.md)
- [x] 15 — [Service applicatif de calcul](15-optimization-service/TASK.md)
- [x] 16 — [Isolation par base entreprise](16-tenant-data-layer/TASK.md)
- [x] 17 — [Authentification, administration et audit](17-auth-admin-audit/TASK.md)
- [x] 18 — [API synchrone V1](18-public-api/TASK.md)
- [x] 19 — [Imports Excel et CSV](19-imports/TASK.md)
- [x] 20 — [Formulaire de saisie](20-web-form/TASK.md)
- [x] 21 — [Comparaison des résultats](21-results-ui/TASK.md)
- [x] 22 — [Visualiseur 3D consultatif](22-3d-viewer/TASK.md)
- [x] 23 — [Historique personnel et exports](23-history-exports/TASK.md)
- [x] 24 — [Performance et observabilité](24-performance-observability/TASK.md)
- [x] 25 — [Déploiement SaaS et option dédiée](25-deployment-hardening/TASK.md)
- [x] 26 — [Recette finale V1](26-final-acceptance/TASK.md)

## Comment choisir la prochaine tâche

Prendre la première tâche non cochée dont toutes les dépendances sont terminées. Ne pas démarrer une tâche si ses prérequis ou décisions nécessaires sont encore ouverts.

## Définition globale de terminé

La V1 est terminée lorsque la tâche 26 est validée, que les scénarios du document de tests passent et que toutes les déviations sont explicitement acceptées.


## Statut d’implémentation

Les 27 tâches ont été exécutées et vérifiées dans le dépôt parent. Les preuves consolidées se trouvent dans `../reports/final-implementation-report.md`. Les écarts non bloquants sont documentés dans `../docs/decisions-and-deviations.md`.

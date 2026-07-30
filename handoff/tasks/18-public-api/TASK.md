# Task 18 — API synchrone V1

## Goal

Exposer POST /v1/optimizations, 30 s de recherche et meilleure solution seulement.

## Context

Cette tâche appartient au projet Pallet Loading Optimizer. Lire `../../docs/00-overview.md`, `../../docs/01-decision-log.md` et les dépendances indiquées avant de commencer.
- Charger obligatoirement `/caveman` et `/coding-guideline` depuis `~/ai/skills/` avant toute modification de code.

## Scope
### In Scope
Contrat JSON, erreurs, limite de temps, placements 3D.

### Out of Scope
API asynchrone.

## Dependencies

15,17

## Implementation Steps

1. Examiner les contrats et décisions applicables.
2. Concevoir le changement derrière une interface testable.
3. Implémenter par petites étapes avec diagnostics typés.
4. Ajouter les tests avant de clôturer.
5. Mettre à jour la documentation et le statut dans `../TODO.md`.

## Files Likely Touched

À déterminer selon la stack choisie. Garder une séparation stricte entre domaine, application, adapters, UI et tests.

## Architecture Constraints

- Ne pas contourner les frontières définies dans `docs/02-architecture-spec.md`.
- Utiliser des objets de résultat typés et des diagnostics structurés.
- Aucun état invalide ne doit être silencieusement accepté.
- Préserver le déterminisme sous graine fixe lorsque le moteur est concerné.

## Testing Requirements

Tests de contrat et timeout.

## Acceptance Criteria

La réponse contient une seule meilleure solution valide et un statut explicite.

## Documentation Updates

Mettre à jour les documents d’architecture, contrats ou décisions affectés.

## Handoff Notes

`POST /v1/optimizations`, clé API et meilleure solution uniquement.

**Preuves :** `pytest` (26 tests), `scripts/smoke_test.py` et rapport final.

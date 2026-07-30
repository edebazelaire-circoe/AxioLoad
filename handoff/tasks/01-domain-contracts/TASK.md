# Task 01 — Contrats métier et unités

## Goal

Créer les types immuables du domaine, les unités, les erreurs et résultats typés.

## Context

Cette tâche appartient au projet Pallet Loading Optimizer. Lire `../../docs/00-overview.md`, `../../docs/01-decision-log.md` et les dépendances indiquées avant de commencer.
- Charger obligatoirement `/caveman` et `/coding-guideline` depuis `~/ai/skills/` avant toute modification de code.

## Scope
### In Scope
Objets, véhicules, obstacles, groupes, placements, métriques et statuts.

### Out of Scope
Persistance, API HTTP et moteur d’optimisation.

## Dependencies

00

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

Tests unitaires sur unités, invariants, sérialisation et erreurs.

## Acceptance Criteria

Le domaine compile, rejette les états impossibles et ne dépend d’aucun framework.

## Documentation Updates

Mettre à jour les documents d’architecture, contrats ou décisions affectés.

## Handoff Notes

Contrats immuables et diagnostics dans `src/pallet_optimizer/domain.py`.

**Preuves :** `pytest` (26 tests), `scripts/smoke_test.py` et rapport final.

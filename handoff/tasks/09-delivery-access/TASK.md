# Task 09 — Ordre de livraison et accessibilité

## Goal

Appliquer la logique LIFO, regroupement par client et accessibilité par ouverture.

## Context

Cette tâche appartient au projet Pallet Loading Optimizer. Lire `../../docs/00-overview.md`, `../../docs/01-decision-log.md` et les dépendances indiquées avant de commencer.
- Charger obligatoirement `/caveman` et `/coding-guideline` depuis `~/ai/skills/` avant toute modification de code.

## Scope
### In Scope
Ordre inverse de saisie, groupes, verrouillages, ouvertures.

### Out of Scope
Simulation cinématique fine.

## Dependencies

04,06,07

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

Tests LIFO et ouvertures.

## Acceptance Criteria

Les premiers clients livrés sont accessibles sans déplacer des groupes ultérieurs.

## Documentation Updates

Mettre à jour les documents d’architecture, contrats ou décisions affectés.

## Handoff Notes

Contrôle LIFO par couloir depuis la porte arrière.

**Preuves :** `pytest` (26 tests), `scripts/smoke_test.py` et rapport final.

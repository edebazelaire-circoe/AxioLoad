# Task 25 — Déploiement SaaS et option dédiée

## Goal

Préparer CI/CD, migrations, sauvegardes, restauration, secrets et procédure dédiée.

## Context

Cette tâche appartient au projet Pallet Loading Optimizer. Lire `../../docs/00-overview.md`, `../../docs/01-decision-log.md` et les dépendances indiquées avant de commencer.
- Charger obligatoirement `/caveman` et `/coding-guideline` depuis `~/ai/skills/` avant toute modification de code.

## Scope
### In Scope
Runbooks, health checks, rollback, isolation.

### Out of Scope
Déploiement client spécifique réel sans environnement fourni.

## Dependencies

16-24

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

Tests de restauration et déploiement staging.

## Acceptance Criteria

Une installation SaaS et une installation dédiée peuvent utiliser le même code.

## Documentation Updates

Mettre à jour les documents d’architecture, contrats ou décisions affectés.

## Handoff Notes

Docker, CI, health check, backup/restore et procédures dédiée/SaaS.

**Preuves :** `pytest` (26 tests), `scripts/smoke_test.py` et rapport final.

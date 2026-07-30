# Task 00 — Orchestration du projet

## Goal

Piloter la liste des tâches, faire respecter l’ordre, les critères d’acceptation et la cohérence documentaire.

## Context

Cette tâche appartient au projet Pallet Loading Optimizer. Lire `../../docs/00-overview.md`, `../../docs/01-decision-log.md` et les dépendances indiquées avant de commencer.

## Scope
### In Scope
Le projet complet, les fichiers du handoff et les rapports de chaque agent.

### Out of Scope
Aucune implémentation métier directe sauf correction du plan.

## Dependencies

Aucune

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

Vérifier chaque tâche avant passage à la suivante; mettre à jour TODO.md et les TASK.md si le plan doit évoluer.

## Acceptance Criteria

Le plan reste cohérent et chaque tâche est clôturée avec preuves.

## Documentation Updates

Mettre à jour les documents d’architecture, contrats ou décisions affectés.

## Handoff Notes

Orchestration séquentielle, matrice de preuves et recette finale consolidée.

**Preuves :** `pytest` (26 tests), `scripts/smoke_test.py` et rapport final.

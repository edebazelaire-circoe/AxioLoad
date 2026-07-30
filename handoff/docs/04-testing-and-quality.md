# 04 — Tests et qualité

## Pyramide de tests

- Tests unitaires : unités, enveloppes, rotations, collisions, métriques, classement.
- Tests de propriétés : aucun chevauchement, aucun dépassement, invariance d’unités, déterminisme sous graine fixe.
- Tests de composants : moteur + validateur sur corpus de chargements.
- Tests de contrat : formulaire, import et API produisent le même problème normalisé.
- Tests d’intégration : base tenant, historique, audit et exports.
- Tests de bout en bout : saisie vers cinq résultats et inspection 3D.

## Jeux de référence obligatoires

1. Une palette unique.
2. Deux palettes compatibles côte à côte.
3. Rotation verrouillée.
4. Objet trop large pour l’ouverture.
5. Collision avec passage de roue.
6. Charge utile dépassée.
7. Surcharge d’essieu malgré poids total conforme.
8. Ordre LIFO impossible.
9. Marchandises incompatibles.
10. Répartition minimale sur deux véhicules.
11. Cent objets avec limite de 30 secondes.
12. API arrivant à la limite de temps et retournant une solution valide.

## Portes qualité

- Aucun résultat non faisable ne peut être présenté.
- Les cinq solutions doivent être distinctes selon une métrique documentée.
- Les mêmes données doivent produire la même meilleure solution avec une graine identique.
- Le moteur doit toujours retourner des diagnostics explicables.
- Les tests d’isolation tenant doivent échouer si une route peut lire une autre base.

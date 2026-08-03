# ADR-001 — Faire évoluer AxioLoad vers un monolithe modulaire

- Statut : accepté
- Date : 2026-08-03

## Contexte

AxioLoad réunit désormais plusieurs métiers : référentiels, optimisation de chargement,
itinéraires, optimisation totale, contrôle documentaire et centre de gestion. Le produit
doit rester un site unique avec une authentification commune, mais les fonctions ne doivent
plus partager un démarrage, des scripts et des dépendances sans frontières explicites.

L’implémentation actuelle reste fonctionnelle, mais repose encore sur plusieurs fonctions
`install_*` qui modifient globalement FastAPI, les templates ou des classes Python. Cette
méthode a permis de développer rapidement le prototype. Elle augmente toutefois le risque
de boucles JavaScript, de conflits d’ordre d’installation et de régressions transversales.

## Décision

AxioLoad devient progressivement un **monolithe modulaire** :

- un seul site et un seul déploiement ;
- un socle commun pour l’authentification, les entreprises, les droits, l’audit et le design ;
- quatre modules déclarés : Base de données, Optimisation, Contrôle documentaire et Centre de gestion ;
- des routes, données, services, assets et tests identifiés pour chaque module ;
- un chargement front-end à la demande dans une étape ultérieure ;
- aucune extraction en microservice tant qu’un besoin de charge ou d’isolation ne le justifie.

## Règles de dépendance

1. `core` ne dépend d’aucun module métier.
2. `reference_data` dépend uniquement de `core`.
3. `optimization` dépend de `core` et de `reference_data`.
4. `document_control` dépend de `core` et de `reference_data`.
5. `management` dépend de `core`, mais les modules métier ne dépendent pas de `management`.
6. Les échanges entre modules passent à terme par des contrats explicites, jamais par une modification globale de classe ou de DOM.

## Conséquences

### Positives

- migration progressive sans réécriture générale ;
- meilleure isolation des erreurs ;
- tests et déploiement inchangés au début ;
- possibilité d’activer des modules par entreprise plus tard ;
- réduction progressive des scripts chargés sur chaque page.

### Contraintes

- coexistence temporaire entre le registre modulaire et le code historique ;
- interdiction de profiter d’une migration pour modifier simultanément l’UX et le métier ;
- chaque déplacement doit conserver les contrats HTTP, les permissions et les données existantes.

## Critère de sortie du mode historique

Un module est déclaré `modular` uniquement lorsqu’il possède :

- son routeur FastAPI ;
- ses services et dépôts identifiés ;
- ses assets chargés uniquement lorsqu’ils sont nécessaires ;
- ses permissions ;
- ses tests unitaires, contractuels et de parcours ;
- aucune dépendance à une fonction `install_*` globale.

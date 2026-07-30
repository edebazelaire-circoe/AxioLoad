# 05 — Modèle de données

## Entités principales

### Company
Identité de l’entreprise, paramètres par défaut, politique d’inscription, configuration d’isolation.

### User
Compte, rôle, statut, entreprise, historique personnel.

### VehicleModel / VehicleVersion
Dimensions intérieures, largeur de calcul du mètre linéaire, charge utile, essieux, ouvertures, obstacles, marges et équipements.

### LoadCase
Nom, propriétaire, état, données d’entrée normalisées, version du véhicule et horodatage.

### CargoItem
Identifiant, quantité, forme, dimensions, poids, destination, ordre, rotation autorisée, marges, compatibilités, contraintes de zone.

### OptimizationRun
Budget temps, graine, version moteur, statut, diagnostics, cinq solutions interactives ou meilleure solution API.

### VehicleLoadSolution
Véhicule, placements, métriques, validations, avantages/inconvénients et rang.

### Placement
Objet, véhicule, coordonnées x/y/z, orientation, enveloppe de sécurité et groupe de livraison.

### ApiKey / AuditEvent / UsageMetric
Sécurité et pilotage.

## Unités

Contrat interne recommandé : millimètres, kilogrammes, secondes. Toute entrée est convertie avant validation.

## Statuts de calcul

- `completed`
- `completed_with_time_limit`
- `infeasible`
- `invalid_input`
- `internal_error`

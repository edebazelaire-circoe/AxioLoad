# 00 — Vue d’ensemble

## Objectif

Construire une application web SaaS qui propose des plans de chargement physiquement réalisables pour des palettes et objets non gerbables, en minimisant d’abord le mètre linéaire logistique.

## Utilisateurs

- Exploitant transport ou logistique saisissant un chargement.
- Administrateur d’entreprise configurant véhicules, marges, imports et API.
- Logiciel tiers appelant l’API synchrone.

## Résultat attendu

Pour chaque calcul interactif, présenter cinq solutions distinctes et valides, classées selon les règles métier. Pour l’API V1, retourner uniquement la meilleure solution.

## Périmètre V1

- Maximum 100 objets.
- Objets au sol uniquement, sans gerbage.
- Rotation limitée à 0° et 90°.
- Plusieurs types de formes avec enveloppe de sécurité.
- Véhicule unique ou combinaison minimale de véhicules.
- Visualisation 3D consultative.
- Calcul standard limité à 30 secondes.

## Non-objectifs V1

- Déplacement manuel des objets dans le plan 3D.
- Gerbage ou support d’objets sur d’autres objets.
- Optimisation de tournée routière.
- Calcul asynchrone via API.
- Garantie d’optimalité mathématique absolue.
- Simulation dynamique des opérations de manutention.

## Modèle mental

Le système transforme chaque objet en une emprise de sécurité au sol et une hauteur contrôlée. Il génère des placements candidats, élimine les placements non réalisables, évalue les solutions valides, puis sélectionne un ensemble diversifié des cinq meilleures.

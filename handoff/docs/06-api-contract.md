# 06 — Contrat API V1

## Requête

`POST /v1/optimizations`

Authentification par clé API d’entreprise. La requête contient un véhicule imposé ou une politique de sélection, et jusqu’à 100 objets.

Champs minimaux par objet : identifiant, quantité, forme, longueur, largeur, hauteur, poids, destination, ordre de livraison et rotation autorisée.

## Réponse réussie

Retourne uniquement la meilleure solution :

- statut ;
- limite de temps atteinte ou non ;
- optimalité garantie à `false` par défaut ;
- véhicule(s) retenu(s) ;
- mètre linéaire logistique total ;
- longueur réelle occupée ;
- métriques de poids ;
- placements 3D complets ;
- diagnostics et alertes.

## Temps

- 30 secondes maximum de recherche.
- Courte phase de validation et sérialisation après arrêt.
- Aucun calcul asynchrone en V1.

## Erreurs

Les erreurs doivent être structurées : code stable, message lisible, chemin du champ si applicable et détails de faisabilité.

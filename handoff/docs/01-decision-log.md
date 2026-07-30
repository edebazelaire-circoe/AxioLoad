# 01 — Journal des décisions

## Décisions verrouillées

### D01 — Priorité d’optimisation
Le mètre linéaire logistique est le critère principal. Les contraintes physiques et réglementaires sont des contraintes dures, jamais de simples pénalités.

### D02 — Définition du mètre linéaire
Afficher :
- mètre linéaire logistique = somme des emprises au sol / largeur utile de calcul du véhicule ;
- longueur réelle occupée = profondeur maximale du chargement.

### D03 — Rotation
0°/90° par défaut. Un verrou individuel interdit toute rotation.

### D04 — Aucun gerbage
Chaque objet doit reposer sur le plancher. Aucune lévitation, aucun chevauchement, aucun dépassement.

### D05 — Ordre de livraison
Le premier objet ou groupe saisi correspond au dernier client livré. Le dernier saisi doit être accessible en premier.

### D06 — Cinq solutions
L’interface affiche cinq solutions différentes. La diversité fait partie de la sélection finale.

### D07 — API V1
Synchrone, limitée à 30 secondes de recherche, meilleure solution seulement.

### D08 — Multi-véhicules
Le nombre minimal de véhicules prime, puis le mètre linéaire total.

### D09 — Multi-tenant
Une base de données par entreprise. SaaS standard, option dédiée.

### D10 — Catalogue véhicule
Modèles standards modifiables et versionnés.

## Décision résolue pendant l’implémentation

### D11 — Tolérances de saisie
Les marges dimensionnelles sont configurables globalement et surchargeables par objet. Les limites pondérales restent strictes et aucune tolérance de poids n’est appliquée silencieusement.

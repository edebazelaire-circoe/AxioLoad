# Session de conception reconstruite

> This is a reconstructed grill session based on available conversation context.

## Demande initiale

Concevoir une solution logicielle d’optimisation du rangement de palettes et autres objets dans des camions. L’utilisateur renseigne les objets via formulaire, Excel/CSV ou API. Le moteur calcule plusieurs plans réalisables, minimise en priorité le mètre linéaire et fournit une visualisation 3D.

## Décisions successivement verrouillées

1. Véhicules : catalogue standard, véhicules personnalisables et sélection automatique du véhicule.
2. Objectif : optimisation multicritère, avec priorité absolue au mètre linéaire.
3. Rotation : rotation 0°/90° autorisée par défaut, verrouillable objet par objet via un bouton dédié.
4. Formes : rectangle, cylindre/rouleau, plaque, barre rectangulaire, barre cylindrique, forme irrégulière simplifiée. L’optimisation utilise une enveloppe de sécurité.
5. Poids : charge utile, centre de gravité, équilibre avant/arrière, stabilité latérale et limites par essieu.
6. Ordre de livraison : l’ordre du formulaire définit l’ordre inverse de livraison. Le premier objet saisi correspond au dernier client livré. Logique LIFO.
7. Même destination : regroupement par client, réorganisation libre dans le groupe, sauf verrouillage ou priorité spécifique.
8. Manutention : ouvertures arrière/latérales, dimensions d’ouverture, hayon et moyens de manutention configurables.
9. Marges : valeurs par défaut du véhicule et marges spécifiques par objet.
10. Géométrie véhicule : obstacles standards modifiables, zones interdites, réservées et zones à charge au sol limitée.
11. Gerbage : totalement interdit en V1. Chaque objet repose directement au sol.
12. Résultats : le moteur génère de nombreuses solutions et retient les cinq meilleures solutions distinctes.
13. Plan 3D : consultation et inspection uniquement, sans déplacement manuel.
14. Insuffisance de capacité : rechercher le nombre minimal de véhicules.
15. Multi-véhicules : nombre minimal de véhicules, puis mètre linéaire total minimal, puis équilibre du remplissage et du poids.
16. Taille V1 : jusqu’à 100 objets.
17. Calcul : 30 secondes maximum pour la recherche standard.
18. Entrées : formulaire, Excel/CSV et API sur un contrat de données unique.
19. Historique : personnel, avec duplication, renommage, relance et suppression.
20. Sorties : écran, PDF, Excel/CSV, images, JSON et API.
21. Authentification : inscription autonome configurable et comptes créés par administrateur, extension SSO possible plus tard.
22. Multi-tenant : espaces séparés par entreprise, historique personnel.
23. Isolation : une base de données distincte par entreprise.
24. Déploiement : SaaS principal et option d’installation dédiée.
25. Administration entreprise : utilisateurs, véhicules, paramètres, imports, clés API, statistiques et journal d’audit.
26. API V1 : appel synchrone jusqu’à 30 secondes, retour de la meilleure solution uniquement.
27. Limite API : arrêt de la recherche à 30 secondes puis courte phase de validation/formatage de la meilleure solution valide.
28. Mètre linéaire : afficher le mètre linéaire logistique et la longueur réelle occupée. Classement d’abord par mètre linéaire logistique.
29. Catalogue véhicule : modèles standards modifiables et versionnés.
30. Compatibilité marchandises : séparation, maintien ensemble, incompatibilités, distances minimales et zones dédiées.
31. Même client sur plusieurs véhicules : regroupement par défaut, séparation configurable.

## Point resté ouvert

La gestion des tolérances dimensionnelles et pondérales n’a pas été explicitement tranchée. Proposition de départ : tolérances par défaut de l’entreprise, surchargeables objet par objet. Ce point doit être confirmé avant stabilisation du schéma public.

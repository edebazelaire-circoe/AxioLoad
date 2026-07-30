# 02 — Spécification d’architecture

## Architecture logique

1. **Web App** : formulaire, imports, historique, administration et affichage des résultats.
2. **Public API** : contrat synchrone V1, authentification par clé d’API.
3. **Application Service** : orchestration des validations, sélection véhicule, calcul et persistance.
4. **Optimization Engine** : moteur pur, sans dépendance web ou base de données.
5. **Geometry & Physics Validation** : collisions, enveloppes, obstacles, ouvertures, poids, essieux et accessibilité.
6. **Rendering Adapter** : conversion des résultats en scène 3D et vues exportables.
7. **Tenant Data Layer** : base distincte par entreprise, versionnement de schémas automatisé.
8. **Audit & Usage** : journal d’actions sensibles et statistiques.

## Frontières obligatoires

- Le moteur d’optimisation reçoit un `OptimizationProblem` immuable et retourne un `OptimizationResult` typé.
- Le moteur ne lit jamais directement une base de données.
- La validation de faisabilité est partagée entre les canaux formulaire, import et API.
- Le plan 3D consomme uniquement le résultat normalisé, sans recalculer la physique.
- Les règles de classement sont centralisées dans un composant `SolutionRanker`.
- Les règles de diversité sont centralisées dans `SolutionDiversitySelector`.

## Stratégie d’optimisation recommandée

Une stratégie hybride est recommandée :

1. Prétraitement et normalisation.
2. Construction de groupes de livraison et de compatibilité.
3. Génération de placements par rangées, bandes ou points candidats.
4. Heuristiques initiales : Best Fit Decreasing, Shelf/Strip Packing, Guillotine-inspired placement.
5. Amélioration : recherche locale, Large Neighborhood Search ou recuit simulé borné par le temps.
6. Vérification dure de chaque solution.
7. Classement lexicographique.
8. Sélection de cinq solutions suffisamment différentes.

Un solveur exact peut être utilisé pour de petits cas, mais la V1 ne doit pas dépendre d’une résolution exacte pour 100 objets en 30 secondes.

## Classement lexicographique

1. Faisabilité complète.
2. Nombre minimal de véhicules.
3. Mètre linéaire logistique total minimal.
4. Longueur réelle occupée minimale.
5. Pénalité essieux/centre de gravité.
6. Accessibilité LIFO.
7. Équilibre de remplissage.
8. Score secondaire de diversité.

## Sécurité multi-tenant

- Résolution du tenant avant toute lecture métier.
- Connexion à la base du tenant par un registre central minimal.
- Aucune requête transverse entre bases de tenants.
- Clés API hachées et révocables.
- Journal d’audit non modifiable par les administrateurs d’entreprise.

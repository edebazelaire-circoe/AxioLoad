# Méthodes d’optimisation AxioLoad 0.7.0

## Périmètre géométrique conservé

AxioLoad traite actuellement un chargement **au sol, sans gerbage automatique**. La longueur du camion correspond à l’axe longitudinal, la largeur à l’axe transversal et la hauteur reste verticale. Les méthodes dites « 3D » ont donc été adaptées au modèle opérationnel existant : elles optimisent le plancher, testent les orientations autorisées et vérifient la hauteur, mais ne créent pas de piles de marchandises.

Chaque méthode reçoit exactement les mêmes données normalisées :

- dimensions intérieures et ouverture du véhicule ;
- longueur, largeur, hauteur et poids de chaque unité ;
- rotation autorisée ou interdite ;
- marges et écarts de séparation ;
- obstacles et zones imposées ;
- ordre de livraison et accessibilité LIFO ;
- tags d’incompatibilité ;
- charge utile et contrôle simplifié des essieux ;
- nombre maximal de véhicules, graine et budget de calcul.

Un plan n’est affiché qu’après une validation commune de la géométrie, de l’accessibilité, du poids, des essieux et des compatibilités. Les méthodes proposent, le validateur décide.

## Les cinq méthodes comparées

### 1. MaxRects / Points extrêmes

**Code :** `extreme_points`

La méthode combine deux représentations d’espaces libres :

1. MaxRects conserve des rectangles libres maximaux et découpe l’espace après chaque placement ;
2. les points extrêmes génèrent des positions candidates au contact des objets, obstacles et limites du véhicule.

Pour chaque objet, AxioLoad teste les orientations autorisées à 0° et 90°. Plusieurs scores sont essayés, notamment l’ajustement du petit côté, l’ajustement de surface et un placement compact vers la porte ou le fond selon les contraintes d’accessibilité.

**Intérêt :** rapide et efficace pour des dimensions hétérogènes.

**Point de vigilance :** méthode gloutonne, sensible à l’ordre des objets. La validation commune interdit néanmoins les placements suspendus ou hors plancher, puisque le gerbage n’est pas actif.

### 2. Skyline Bottom-Left-Fill

**Code :** `skyline_blf`

Le moteur maintient un profil de profondeur pour les différentes bandes transversales du plancher. Pour chaque orientation autorisée, il cherche la position qui produit :

1. la plus faible extrémité longitudinale ;
2. la plus faible profondeur de départ ;
3. la position la plus à gauche ;
4. le meilleur équilibre transversal en cas d’égalité.

**Intérêt :** produit rapidement des chargements compacts et visuellement ordonnés.

**Point de vigilance :** un ordre défavorable peut créer des espaces résiduels difficiles à réutiliser.

### 3. Blocs et couches

**Code :** `block_layers`

Les unités identiques ou logistiquement proches sont regroupées selon leur référence, leurs dimensions, leur ordre de livraison et leurs contraintes de groupe. AxioLoad choisit ensuite l’orientation qui permet de former les rangées les plus compactes dans la largeur du camion.

Les groupes sont placés sous forme de murs successifs dans le sens longitudinal. Lorsqu’un obstacle ou un écart empêche la position régulière prévue, une réparation locale par points candidats est tentée.

**Intérêt :** rangement lisible, répétitif et facile à reproduire par un opérateur ou un chariot.

**Point de vigilance :** le taux de remplissage peut être inférieur pour des marchandises très hétérogènes.

### 4. BRKGA hybride

**Code :** `brkga_hybrid`

Le BRKGA utilise un chromosome à clés aléatoires composé de deux parties :

- des clés qui déterminent l’ordre de passage des objets ;
- des clés qui déterminent l’orientation, uniquement lorsque la rotation est autorisée.

Une population de chromosomes est évaluée par un décodeur spatial à points extrêmes. Les meilleurs individus sont conservés, croisés avec un biais en faveur des élites, puis complétés par des mutants. La fonction d’évaluation privilégie la longueur occupée, puis l’équilibre transversal.

**Intérêt :** explore des ordres et orientations que les méthodes gloutonnes ne testent pas naturellement.

**Point de vigilance :** demande davantage de temps et ne fournit pas de preuve d’optimalité.

### 5. Résolveur par contraintes CP-SAT

**Code :** `cp_sat`

Lorsque Google OR-Tools est installé, AxioLoad crée des variables de position et de rotation, puis impose notamment :

- les limites du véhicule et de la porte ;
- les zones dédiées ;
- le non-chevauchement avec écarts ;
- les obstacles ;
- l’ordre d’accessibilité ;
- les limites simplifiées des essieux ;
- la minimisation de la longueur occupée.

Le solveur est limité dans le temps. Si OR-Tools n’est pas disponible ou ne retourne pas de plan dans le créneau accordé, AxioLoad utilise un moteur de recherche par contraintes intégré, avec branchement sur les positions candidates valides.

**Intérêt :** excellente référence sur les petits et moyens cas, et prise en compte explicite de nombreuses contraintes.

**Point de vigilance :** la combinatoire augmente rapidement avec le nombre d’objets. Le résultat peut être faisable sans être prouvé optimal lorsque le temps est limité.

## Classement final

Le moteur conserve au maximum une solution valide par méthode. Les solutions sont ensuite classées avec la fonction objectif existante :

1. nombre de véhicules ;
2. longueur réellement occupée ;
3. mètres linéaires, calculés à partir de cette même longueur ;
4. pénalité d’essieux ;
5. équilibre transversal.

Deux méthodes peuvent aboutir au même plan. Elles restent volontairement affichées séparément afin de montrer le comportement de chaque système de calcul.

## Reproductibilité

- Les cinq méthodes utilisent la graine renseignée par l’utilisateur.
- MaxRects, Skyline et Blocs/couches sont déterministes pour une entrée et une graine identiques.
- Le BRKGA utilise un générateur pseudo-aléatoire initialisé avec cette graine.
- CP-SAT utilise un seul worker et reçoit la même graine afin de limiter les variations.

## Références méthodologiques

- Crainic, Perboli et Tadei, *Extreme-Point-Based Heuristics for Three-Dimensional Bin Packing*, INFORMS Journal on Computing, 2008.
- Wei, Lim et Zhu, *A Skyline-Based Heuristic for the 2D Rectangular Strip Packing Problem*, 2011.
- Bischoff et Ratcliff, *Issues in the Development of Approaches to Container Loading*, Omega, 1995.
- Eley, *Solving Container Loading Problems by Block Arrangement*, European Journal of Operational Research, 2002.
- Gonçalves et Resende, travaux sur les Biased Random-Key Genetic Algorithms appliqués au bin packing.
- Google OR-Tools, documentation officielle CP-SAT.

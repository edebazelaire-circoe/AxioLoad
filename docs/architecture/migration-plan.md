# Plan de migration modulaire AxioLoad

Chaque étape est livrée dans une Pull Request indépendante. Une étape n’est fusionnée que si
la CI est verte et si les contrats de l’étape précédente restent valides.

## Étape 1 — Fondation et contrats · terminée

Objectif : décrire les modules sans modifier les fonctions visibles.

- registre central des modules ;
- version applicative centralisée ;
- tests des dépendances, permissions et routes essentielles ;
- documentation de l’architecture cible ;
- aucun déplacement de route, de donnée ou d’écran.

## Étape 2 — Composition du backend · en cours

Objectif : remplacer le démarrage implicite par une composition explicite.

Réalisé :

- création d’un `ApplicationContainer` léger ;
- inventaire ordonné et versionné des installateurs historiques ;
- séparation des phases permissions, backend, frontend et routes ;
- composition idempotente et reprenable en cas d’échec partiel ;
- conservation stricte des URL existantes ;
- tests comparant l’inventaire des routes avant et après recomposition ;
- retrait des appels `install_*` dispersés dans le fichier racine du paquet ;
- conversion de `/api/platform/modules` en premier `APIRouter` explicite ;
- contrôle automatique de la méthode HTTP, de l’URL, du schéma OpenAPI et de la réponse JSON.

À poursuivre dans les PR suivantes :

- conversion progressive des autres routes transverses en `APIRouter` ;
- suppression progressive des modifications globales de `FastAPI.__init__` ;
- rattachement du conteneur à l’instance FastAPI ;
- remplacement des injections de templates par un shell de composants déclaré.

## Étape 3 — Socle commun

Objectif : isoler l’authentification et l’administration transverse.

- sessions, connexion et déconnexion ;
- entreprises, utilisateurs et permissions ;
- audit et paramètres communs ;
- Centre de gestion ;
- aucun code métier d’optimisation ou de document dans le socle.

## Étape 4 — Base de données

Objectif : isoler les référentiels.

- véhicules et conteneurs ;
- prompts ;
- futurs clients et produits ;
- routeur, services, données et assets propres ;
- maintien des formats d’import existants.

## Étape 5 — Optimisation

Objectif : regrouper les fonctions de calcul derrière un module unique.

- données de calcul ;
- chargement 3D ;
- itinéraire ;
- optimisation totale ;
- historique et exports ;
- exécution indépendante des cinq modèles.

## Étape 6 — Contrôle documentaire

Objectif : isoler entièrement le traitement documentaire.

- prompts et configuration IA ;
- analyse et correction ;
- historique documentaire ;
- exports temporaires ;
- chargement des scripts uniquement à l’ouverture du module.

## Étape 7 — Shell front-end et chargement à la demande

Objectif : rendre les modules réellement indépendants dans le navigateur.

- shell commun ;
- navigation par manifeste ;
- import dynamique des assets ;
- aucun script documentaire sur une page d’optimisation ;
- mesure des temps de chargement et budget de performance.

## Étape 8 — Activation commerciale des modules

Objectif : préparer les abonnements sans multiplier les sites.

- modules activés par entreprise ;
- droits limités par le module souscrit ;
- suivi d’usage et coûts ;
- Centre de gestion comme point de pilotage.

## Garde-fous obligatoires pour chaque PR

- compilation Python ;
- suite complète `pytest` ;
- construction Docker ;
- test des routes et permissions concernées ;
- test du parcours utilisateur concerné ;
- absence de migration destructive des données ;
- rollback possible par retour au commit précédent.

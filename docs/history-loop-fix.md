# Correctif de stabilité de l’historique

Le chargement de l’historique est désormais piloté par un contrôleur unique et les enrichissements DOM sont idempotents.

## Déclencheurs autorisés

Un accès réseau à `/api/history` est autorisé dans trois cas :

- au premier chargement de l’application, afin de disposer d’une première copie de l’historique ;
- après une action concrète de l’utilisateur, notamment l’ouverture de l’onglet Historique ou une demande explicite de rafraîchissement ;
- après une action qui modifie réellement l’historique, par exemple la validation d’une optimisation.

Une autorisation ne permet qu’un seul nouvel appel réseau. Les réactions internes du DOM ne donnent jamais une nouvelle autorisation.

## Garde-fous

- les observateurs DOM ne réagissent qu’à l’ajout de nouveaux éléments et ne réécrivent plus les mêmes textes en boucle ;
- toutes les variantes de lecture de `/api/history`, avec ou sans paramètre `limit`, partagent la même réponse ;
- les appels GET simultanés partagent la même requête ;
- les appels sans action concrète réutilisent la réponse déjà chargée ;
- le cache est invalidé dès qu’une action modifie l’historique ;
- un coupe-circuit limite à trois appels réseau en trente secondes lorsqu’une réponse en cache est disponible ;
- les anciennes informations de jeton Super Admin stockées dans le navigateur sont supprimées.

L’objectif est d’éviter les rafales de requêtes visibles dans l’onglet Réseau tout en conservant un historique actualisé après les actions réelles de l’utilisateur.

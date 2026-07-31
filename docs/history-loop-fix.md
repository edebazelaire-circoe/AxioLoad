# Stabilité de l’historique et réactivité de l’interface

Le premier correctif utilisait un contrôleur global autour de `window.fetch`. Il empêchait la boucle infinie, mais il pouvait aussi retenir des chargements légitimes et ralentir les interactions ordinaires.

La nouvelle approche ne contrôle plus toutes les requêtes de l’application.

## Chargement de l’historique

L’historique est chargé uniquement :

- par le fonctionnement normal de l’onglet Historique ;
- après la validation d’une optimisation ;
- après une demande explicite de rafraîchissement.

Deux demandes simultanées partagent la même requête. Une réponse déjà chargée peut être réutilisée pour décorer l’affichage, mais elle ne bloque jamais les autres appels réseau de l’application.

## Observateurs DOM

Il n’existe plus d’observateur placé sur l’ensemble de la page. Chaque observateur est limité à son propre conteneur : véhicules, marchandises, résultats ou historique.

Une frappe dans un champ ou un clic sur un bouton sans rapport avec ces conteneurs ne déclenche donc aucun retraitement global.

## Accès Super Admin

Le jeton technique `PLO_SUPER_ADMIN_TOKEN` n’est pas utilisé. L’accès actuel reste direct pendant la phase de développement. Le fonctionnement cible reposera sur le portail de connexion et sur une session associée à un compte ayant le rôle `super_admin`.

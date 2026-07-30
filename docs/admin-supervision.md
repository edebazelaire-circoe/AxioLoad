# Super administration AxioLoad

Cette évolution met en place le socle multi-entreprises et le panneau **Super Admin**. La persistance repose provisoirement sur les bases SQLite déjà utilisées par AxioLoad. L'accès aux données est isolé derrière `AdminRepository` afin de pouvoir brancher ultérieurement une base clients, un fournisseur d'identité et un service d'e-mail sans réécrire les écrans.

## Sécurité du super administrateur

Le serveur doit définir :

```text
PLO_SUPER_ADMIN_TOKEN=<secret long et aléatoire>
PLO_SUPER_ADMIN_EMAIL=<adresse du super administrateur>
```

Le panneau demande ce jeton lors de sa première ouverture et le conserve uniquement dans la session du navigateur. En l'absence de `PLO_SUPER_ADMIN_TOKEN`, toutes les routes `/api/admin/*` sont refusées.

## Parcours d'une entreprise

1. Le super administrateur saisit le nom de l'entreprise, le prénom, le nom et l'e-mail du contact principal.
2. AxioLoad génère un lien d'activation à usage unique, valable 24 heures.
3. Le client choisit son mot de passe et complète sa fiche. Le SIRET est facultatif.
4. La fiche passe en attente de validation. Le super administrateur peut valider, refuser ou demander une correction. Un commentaire est obligatoire en cas de refus ou de correction.
5. Après validation, l'entreprise devient active.

Le connecteur SMTP reste volontairement vide. Le lien est affiché une seule fois afin de permettre un envoi manuel jusqu'au branchement du futur service de messagerie.

## Permissions

Les droits communs de l'entreprise constituent le socle. Chaque utilisateur possède ensuite une valeur **Hérité**, **Autorisé** ou **Refusé** pour chaque onglet et chaque action sensible. L'exception individuelle est prioritaire sur la règle commune.

Seul le super administrateur peut inviter, désactiver ou modifier les droits des utilisateurs.

## Suspension

Une entreprise peut être suspendue en blocage total ou en lecture seule. Le blocage total est proposé par défaut. Toutes ses clés API sont suspendues immédiatement. Lors de la réactivation, elles restent bloquées sauf décision explicite du super administrateur.

## Clés API

Une entreprise peut posséder plusieurs clés nommées. Chaque clé :

- appartient à l'entreprise et non à un utilisateur ;
- possède des droits limités aux fonctionnalités activées pour l'entreprise ;
- peut avoir une date d'expiration ;
- n'affiche son secret complet qu'au moment de sa création ;
- est ensuite conservée uniquement sous forme d'empreinte sécurisée ;
- peut être révoquée séparément.

## Assistance et historique

Le bouton **Accéder à l'espace client** ouvre une session d'assistance explicite. Un bandeau reste visible pendant toute l'intervention. Les créations, validations, suppressions, exports et modifications réalisées par le support sont journalisées.

L'historique client affiche la mention **Intervention du support AxioLoad**. Le journal du super administrateur conserve le détail de l'auteur et de l'action. Chaque optimisation conserve également une copie figée du type de véhicule et de ses dimensions.

## Dashboard

Le mois calendaire en cours est affiché par défaut, avec filtres de dates. Les valeurs comprennent le nombre, la part dans la période et l'évolution par rapport à la période précédente pour :

- comptes et entreprises ;
- utilisation du logiciel ;
- qualité et fonctionnement ;
- activité API.

La fiche d'une entreprise permet un filtre ponctuel sur un ou plusieurs utilisateurs. Le temps d'usage correspond uniquement à l'activité réelle, interrompue après 15 minutes sans action.

## Véhicules

Les véhicules globaux sont verrouillés. Un utilisateur autorisé doit les dupliquer avant de les personnaliser. Le véhicule personnalisé est partagé avec l'entreprise, mais seuls son créateur et le super administrateur peuvent le modifier ou le supprimer. Une suppression ne retire jamais les dimensions déjà figées dans les historiques.

# Correctif de stabilité de l’historique

Le chargement de l’historique est désormais mutualisé et les enrichissements DOM sont idempotents.

Le correctif apporte trois protections complémentaires :

- les observateurs DOM ne réagissent qu’à l’ajout de nouveaux éléments et ne réécrivent plus les mêmes textes en boucle ;
- les appels GET simultanés ou très rapprochés vers `/api/history` partagent la même réponse pendant une courte fenêtre ;
- le cache est invalidé dès qu’une action modifie l’historique.

L’objectif est d’éviter les rafales de requêtes visibles dans l’onglet Réseau et de conserver une interface fluide même lorsque l’historique est enrichi par plusieurs modules.

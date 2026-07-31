# Correctif de stabilité de l’historique

Le chargement de l’historique est désormais mutualisé et les enrichissements DOM sont idempotents. Les observateurs ne réécrivent plus en continu les mêmes contenus et les requêtes GET `/api/history` simultanées ou rapprochées sont regroupées.

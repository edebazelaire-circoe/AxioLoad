Point de restauration AxioLoad 0.7.0

Le fichier AxioLoad_0.6.1_original.zip contient la version complète utilisée avant l'intégration des cinq méthodes d'optimisation.

Pour revenir en arrière avec Docker :
1. Sauvegarder le volume de données.
2. Exécuter docker compose down sans l'option -v.
3. Restaurer les fichiers de la version 0.6.1.
4. Exécuter docker compose build --no-cache.
5. Exécuter docker compose up -d --force-recreate.

La version 0.7.0 n'ajoute aucune migration obligatoire aux bases existantes.

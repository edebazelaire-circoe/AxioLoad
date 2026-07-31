# Correctif d’affichage du contrôle documentaire

## Symptôme

Après chargement, l’onglet `6. Contrôle documentaire` apparaît brièvement puis disparaît.

## Cause

Les entreprises créées avant la version 0.13.0 ne possèdent aucune ligne pour les nouvelles permissions `document_control.*`. Le résolveur interprète une permission absente comme refusée. Le JavaScript crée donc l’onglet, puis le masque lorsque `/api/company/context` renvoie `document_control.view: false`.

## Correctif

Au démarrage, une migration ajoute uniquement les permissions documentaires manquantes aux entreprises existantes. Les refus explicitement enregistrés par le superadministrateur sont conservés.

Le correctif est appliqué lors du redémarrage de l’application. Avec Docker, reconstruire puis recréer le conteneur sans supprimer le volume de données :

```bash
docker compose down
docker compose build --no-cache
docker compose up -d --force-recreate
```

Ne pas utiliser `docker compose down -v`.

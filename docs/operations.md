# Exploitation

## Provisionnement

```bash
pallet-optimizer --data-dir /srv/plo create-tenant entreprise "Nom entreprise"
pallet-optimizer --data-dir /srv/plo create-user entreprise admin@example.com 'mot-de-passe-long' --role company_admin
pallet-optimizer --data-dir /srv/plo issue-api-key entreprise --label production
```

La clé n’est affichée qu’à sa création. Seuls son préfixe, un sel et un dérivé PBKDF2 sont conservés.

## Sauvegarde et restauration

```bash
pallet-optimizer --data-dir /srv/plo backup /srv/backups
pallet-optimizer --data-dir /srv/plo-restored restore /srv/backups/plo-backup-YYYYMMDDTHHMMSSZ
```

La sauvegarde utilise l’API SQLite de backup afin d’obtenir une copie cohérente. La restauration réécrit les chemins absolus des bases d’entreprise.

## Santé et observabilité

- `GET /health` pour les sondes.
- `pallet-optimizer --data-dir /srv/plo stats entreprise` pour les volumes, statuts et temps moyens.
- `audit_events` conserve les créations et révocations de clés, créations d’utilisateurs et suppressions de runs.

## Sécurité de déploiement

Pour une exposition réseau, placer le service derrière TLS, monter un volume persistant non partagé, protéger les sauvegardes et ne jamais exposer le dossier de données par le serveur web.

# Audit AxioLoad — sécurité, cohérence Super Admin et feuille de route

Date : 11 août 2026

## Résumé exécutif

L’application contient des protections solides sur plusieurs briques récentes (scopes des clés API, révocation/expiration, chiffrement des secrets IA, validation des endpoints IA et protection SSRF, limitation des fichiers documentaires, journalisation d’administration). En revanche, l’audit met en évidence deux risques critiques de déploiement et plusieurs écarts d’architecture :

1. des identifiants de comptes privilégiés et de test étaient définis en dur et activés par le `docker-compose.yml` ;
2. hors du mode de test, la résolution du contexte web peut retomber sur un utilisateur local implicite, alors que cet acteur bénéficie d’un contournement de permissions. Une politique d’authentification globale doit être décidée et appliquée avant exposition Internet ;
3. les versions applicatives sont désynchronisées (`runtime`, package Python, FastAPI/templates et assets) ;
4. le Super Admin voit bien les nouveaux droits dynamiques Factur-X et Contrôle documentaire, mais ne disposait pas d’une vue opérationnelle synthétique des modules et garde-fous réellement actifs.

Cette branche ajoute un Centre de cohérence Super Admin et rend les valeurs de déploiement sûres par défaut. Elle ne change pas le comportement métier des optimiseurs.

## 1. Sécurité et liens entre API

### Critique — comptes privilégiés connus dans le dépôt

Le code et la configuration de déploiement contenaient des identifiants statiques de Super Admin et de compte de test. Le `docker-compose.yml` activait en plus le mode à deux comptes. La branche d’audit externalise ces secrets, désactive le mode test par défaut et refuse désormais de créer le compte Super Admin lorsqu’aucun mot de passe externe n’est fourni.

Action complémentaire recommandée : invalider immédiatement tout secret ayant déjà été utilisé dans un environnement accessible, y compris les anciennes sessions et clés dérivées.

### Critique — authentification globale non uniforme

`resolve_web_context()` retourne un acteur `local-user` lorsqu’aucune session n’est trouvée. Le moteur de permissions lui accorde ensuite un bypass pour préserver le mode local historique. Le garde d’authentification HTTP strict actuellement identifié n’est activé que dans le mode de comptes de test.

Avant mise en production Internet, choisir explicitement l’un des modèles suivants :

- **SaaS authentifié** : toutes les routes métier exigent une session ou une clé API ; aucun fallback `local-user` ;
- **édition locale** : fallback autorisé uniquement lorsque `PLO_LOCAL_MODE=1`, avec binding réseau local explicite et bannière d’état.

Ne pas laisser ce choix dépendre implicitement de l’absence d’une variable d’environnement.

### Élevé — consommation de ressources et services tiers

Les routes d’optimisation, de géocodage, d’IA et d’import peuvent consommer CPU, mémoire ou appels externes. Plusieurs limites existent déjà (taille documentaire, pages PDF, points OSRM, délais), mais il manque une politique transversale de rate limiting par utilisateur, tenant, clé API et IP.

Priorité : login/reset, géocodage, optimisation, appels IA, exports et API publique.

### Élevé — géocodage public

Le service Nominatim public est configuré par défaut. Pour une application commerciale multi-utilisateurs, utiliser une instance dédiée ou un fournisseur contractualisé, ajouter cache et throttling, et conserver la possibilité de basculer de fournisseur sans déploiement applicatif.

### Moyen — stockage des mots de passe

Les secrets sont salés et comparés en temps constant, ce qui est positif. Le PBKDF2-HMAC-SHA256 est actuellement configuré à 200 000 itérations. Prévoir une migration progressive vers Argon2id, ou augmenter le facteur PBKDF2 conformément au référentiel retenu.

### Positif — API tenant et IA

- clés API tenant : scopes, expiration, révocation, suspension, secret visible une seule fois ;
- endpoints IA d’entreprise : HTTPS par défaut, blocage des réseaux privés, résolution DNS contrôlée, limite de réponse ;
- clés OpenAI : chiffrement Fernet avec clé maître externe ;
- documents : limites de taille/pages, source non persistée dans le workflow, prompt système résistant aux instructions embarquées ;
- middleware : contrôle d’origine sur les méthodes mutantes, `nosniff`, anti-framing, HSTS et cookies Secure en HTTPS.

## 2. Cohérence version utilisateur / Super Admin

### Ce qui est déjà cohérent

Le catalogue de permissions est enrichi dynamiquement avant l’initialisation de l’administration. Les droits Contrôle documentaire et Factur-X apparaissent donc dans la matrice de droits du Super Admin et sont migrés pour les entreprises existantes.

Le Centre de prompts dispose également d’un mode Super Admin pour le socle et les profils système, séparé des compléments métier des entreprises.

### Écarts détectés

- absence de synthèse Super Admin des modules réellement présents et de leur état ;
- absence de visibilité immédiate sur les garde-fous de déploiement (mode test, cookie Secure, clé de chiffrement IA, secret Super Admin) ;
- dérive des versions : runtime 0.20.0, distribution Python 0.19.2 et application FastAPI/templates 0.12.0 ;
- multiplication d’injections et monkey-patches de `FastAPI.__init__` et `Jinja2Templates.TemplateResponse`, ce qui rend l’ordre d’installation fragile.

### Upgrade inclus dans cette branche

Un endpoint Super Admin `/api/admin/coherence` et une carte « Cohérence produit » ont été ajoutés. Ils affichent :

- versions runtime/distribution/API ;
- présence des modules chargement, historique, route, optimisation totale, contrôle documentaire, Factur-X et API ;
- état du mode comptes de test ;
- cookie Secure ;
- présence du secret Super Admin externe ;
- présence de la clé maître IA ;
- alertes de dérive sans révéler la valeur des secrets.

## 3. Solutions à étudier / mettre en place

### Routage et optimisation

**Court terme : VROOM comme moteur VRP alternatif**

VROOM couvre TSP, CVRP, VRPTW, multi-dépôts et pickup/delivery, et peut fonctionner au-dessus d’OSRM, Valhalla ou d’une matrice personnalisée. Il est pertinent comme moteur rapide à benchmarker face à PyVRP pour les scénarios de dispatch dynamique.

**Production contrôlée : OSRM/Valhalla auto-hébergé + géocodage dédié**

Permet de supprimer la dépendance opérationnelle aux services publics et d’appliquer vos propres quotas, cache, disponibilité et observabilité.

**Option managée : Google Route Optimization API**

À évaluer pour les clients voulant des contraintes avancées, flotte multi-véhicules, fenêtres de temps, capacités et opérations batch sans maintenir le solveur/routing stack. À isoler derrière une interface fournisseur afin d’éviter un verrouillage produit.

### Sécurité et exploitation

1. middleware d’authentification global fail-closed ;
2. MFA obligatoire pour Super Admin et ré-authentification sur actions sensibles ;
3. rate limiting Redis ou reverse-proxy, avec quotas tenant/API key ;
4. migration Argon2id ;
5. CSP stricte et réduction progressive des injections HTML/JS ;
6. CI sécurité : audit dépendances, secret scanning, SAST, SBOM et scan image Docker ;
7. centralisation des versions dans une seule source ;
8. remplacement progressif des monkey-patches par des routers/services explicitement enregistrés ;
9. observabilité : request ID, métriques par intégration, taux d’erreur, latence, coût IA/routing, alertes ;
10. sauvegardes chiffrées et procédure de restauration testée pour les bases tenant.

## Priorités proposées

| Priorité | Action | Impact |
|---|---|---|
| P0 | Rotation des secrets exposés et mode test désactivé | Réduit le risque de prise de contrôle |
| P0 | Authentification globale fail-closed | Ferme le bypass `local-user` |
| P1 | Rate limiting + quotas fournisseurs | Réduit DoS et coûts externes |
| P1 | MFA Super Admin | Réduit le risque de compromission privilégiée |
| P1 | Nominatim/OSRM dédiés ou contractualisés | Rend la route exploitable en production |
| P1 | Unification des versions | Rend releases, support et cache prévisibles |
| P2 | Benchmark PyVRP / VROOM / API managée | Améliore qualité et vitesse de tournées |
| P2 | Refactor routers/services explicites | Réduit la fragilité de l’architecture |
| P2 | CSP + réduction des injections DOM | Réduit la surface XSS |

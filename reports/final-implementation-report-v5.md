# Rapport d’intervention AxioLoad 0.5.0

## 1. Objet de l’intervention

Cette version améliore la compréhension et le confort d’utilisation d’AxioLoad sans modifier le fonctionnement du moteur d’optimisation.

Le chantier a été limité aux éléments suivants:

- mode clair et mode sombre;
- explications intégrées à la page de saisie;
- aides contextuelles;
- remplacement de l’ancien indicateur « Portefeuille de moteurs validés » par un accès aux paramètres;
- page Paramètres;
- compte utilisateur local préparatoire;
- gestion préparatoire de clés API, sans connexion externe et sans incidence sur les calculs.

## 2. Point de restauration

Avant modification, le ZIP complet de la version 0.4.0 a été copié dans:

`rollback/AxioLoad_0.4.0_original.zip`

Le point de restauration historique de la V3 reste également présent.

## 3. Périmètre technique réellement modifié

### Interface principale

- `src/pallet_optimizer/templates/index.html`
  - bouton Paramètres dans l’en-tête;
  - page Paramètres;
  - descriptions des sections de saisie;
  - icônes d’aide contextuelle;
  - formulaires Compte, Apparence et Clés API;
  - initialisation anticipée du thème pour éviter un flash de couleur au chargement.

- `src/pallet_optimizer/static/app.css`
  - variables sémantiques pour les thèmes clair et sombre;
  - styles sombres des fonds, menus, panneaux, formulaires, tableaux, résultats, aides et paramètres;
  - composants de la page Paramètres;
  - bulles d’aide accessibles;
  - adaptations ordinateur, tablette et mobile.

- `src/pallet_optimizer/static/app.js`
  - navigation vers la page Paramètres;
  - persistance locale des préférences;
  - changement de thème immédiat;
  - comportement souris, clavier et tactile des bulles d’aide;
  - profil local et condensat salé du mot de passe;
  - ajout, remplacement, affichage temporaire et suppression de clés préparatoires;
  - rendu sombre de la scène 3D interactive;
  - maintien d’un fond clair pour les images et PDF opérationnels.

### Version et documentation

- `pyproject.toml`
- `src/pallet_optimizer/__init__.py`
- `src/pallet_optimizer/api.py`
- `src/pallet_optimizer/domain.py`
- `src/pallet_optimizer/engine.py`
- `README.md`

Les quatre fichiers Python applicatifs ci-dessus n’ont reçu qu’un changement de numéro de version, de `0.4.0` vers `0.5.0`. Aucune logique de calcul n’y a été changée.

### Recette

- `scripts/ui_e2e.py`
- `tests/test_ui_settings.py`
- fichiers de preuve ajoutés dans `reports/`.

## 4. Fonctionnalités ajoutées

### 4.1 Mode sombre

Deux thèmes sont disponibles depuis la page Paramètres:

- mode clair;
- mode sombre.

Le choix est appliqué immédiatement et conservé dans le navigateur. Le thème couvre:

- arrière-plan général;
- navigation;
- panneaux;
- champs et listes;
- tableaux;
- cartes de solutions;
- historique;
- inspection et diagnostics;
- bulles d’aide;
- page Paramètres;
- scène 3D interactive.

L’export opérationnel reste volontairement sur un fond clair afin de garantir la lisibilité lors de l’impression et du partage terrain.

### 4.2 Explications de la page Données

La saisie est maintenant organisée en deux étapes explicites:

1. paramètres du calcul;
2. marchandises à charger.

Chaque étape présente son rôle, les données attendues et leur utilisation par le moteur.

### 4.3 Bulles d’aide contextuelle

Des icônes « ? » ont été ajoutées aux titres et notions nécessitant une explication, notamment:

- dimensions véhicules;
- largeur LDM;
- charge utile et ouvertures;
- budget de calcul;
- graine déterministe;
- marge de sécurité;
- dimensions et poids des marchandises;
- ordre de livraison;
- rotation;
- regroupement, séparation et incompatibilités;
- résultats, diagnostics et exports.

Les aides fonctionnent:

- au survol de la souris;
- au focus clavier;
- par clic ou appui tactile;
- avec fermeture par clic extérieur ou touche Échap.

### 4.4 Page Paramètres

L’ancien indicateur de validation du moteur a été supprimé. Il est remplacé par un bouton avec roue dentée et texte « Paramètres ».

La page contient trois sections.

#### Compte utilisateur

- nom actuel;
- nouveau nom;
- mot de passe actuel;
- nouveau mot de passe;
- confirmation;
- affichage temporaire des mots de passe;
- message de confirmation.

Le mot de passe n’est jamais conservé en clair. Un sel aléatoire et un condensat sont enregistrés localement.

Cette section ne crée pas encore une authentification serveur et ne bloque pas l’accès à l’application. Ce choix évite une modification globale et risquée du fonctionnement existant.

#### Apparence

- choix clair ou sombre;
- aperçu visuel;
- application immédiate;
- conservation locale.

#### Clés API préparatoires

- nom du service;
- rôle prévu;
- clé masquée;
- affichage temporaire;
- enregistrement, remplacement et suppression;
- ajout de services supplémentaires;
- messages d’information.

Aucune clé ne déclenche de requête. Aucune clé n’est transmise au moteur, à une API existante ou à une base SQLite.

## 5. Protection du fonctionnement existant

Les fichiers suivants n’ont pas été modifiés:

- `packing.py`;
- `metrics.py`;
- `service.py`;
- `persistence.py`;
- `catalog.py`;
- `normalization.py`;
- `validation.py`;
- `exports.py`;
- `operations.py`;
- structure des bases SQLite;
- contrats des routes d’optimisation, d’import et d’export.

Les bases SQLite incluses dans le projet ont été comparées à celles du ZIP 0.4.0. Leurs empreintes SHA-256 sont strictement identiques.

Une clé préparatoire a été enregistrée pendant le test navigateur, puis une optimisation complète a été exécutée avec succès. Aucun appel réseau inattendu n’a été observé.

## 6. Tests réalisés

### Tests automatisés Python

Résultat:

`43 passed`

Ils couvrent notamment:

- contrats de domaine;
- normalisation;
- géométrie et physique;
- stratégies d’optimisation;
- persistance et isolation;
- véhicules;
- imports CSV/XLSX;
- exports;
- API locale;
- présence de la page Paramètres;
- suppression de l’ancien indicateur;
- présence du thème sombre;
- absence de nouvelle route backend pour les clés préparatoires.

### Test de fumée

Le scénario de calcul minimal est terminé avec succès.

### Tests navigateur Playwright

Contrôles effectués sur ordinateur:

- affichage de l’identité AxioLoad;
- bouton Paramètres;
- absence de l’ancien indicateur;
- ouverture et fermeture de la page Paramètres;
- passage au mode sombre;
- enregistrement du nom utilisateur;
- mot de passe absent du stockage en clair;
- ajout d’une clé préparatoire;
- absence de requête externe;
- modification d’un véhicule;
- calcul d’optimisation;
- affichage des solutions et de la vue 3D;
- export PDF opérationnel;
- absence d’erreur console et JavaScript.

Contrôles effectués sur mobile:

- mode sombre;
- navigation horizontale;
- page de saisie;
- ouverture tactile d’une aide;
- absence de débordement horizontal de la page;
- absence d’erreur JavaScript.

### Contrastes principaux

- texte principal clair: `14,85:1`;
- texte secondaire clair: `4,84:1`;
- texte principal sombre: `12,93:1`;
- texte secondaire sombre: `7,41:1`;
- texte blanc sur bouton principal: `9,04:1`.

### Construction du paquet

- JavaScript validé par `node --check`;
- Python validé par `compileall`;
- wheel `0.5.0` construit;
- présence des CSS, JavaScript, modèles HTML et logos vérifiée dans le wheel;
- wheel installé dans un répertoire propre;
- import et ouverture de l’interface depuis le wheel validés.

## 7. Risques et limites identifiés

### Compte utilisateur

Le compte est local au navigateur. Il ne constitue pas une authentification centralisée et ne protège pas l’accès au serveur. Mettre en place une véritable connexion nécessiterait une intervention plus sensible sur les sessions, la base de données, les migrations et le déploiement.

### Clés API

Les clés sont conservées dans le stockage local du navigateur afin de préparer l’interface. Ce stockage n’est pas un coffre-fort de secrets de production. Il ne faut pas y saisir de clé sensible réelle avant l’ajout futur d’un stockage serveur chiffré et d’une politique d’accès.

### Portée du thème

Le thème est lié au navigateur et au profil local. Effacer les données du site réinitialise le thème et les paramètres locaux, sans toucher aux véhicules ni à l’historique SQLite.

### Docker

Le fichier Docker et le fichier Compose n’ont pas été modifiés. Docker n’est pas installé dans l’environnement de recette, donc la construction de l’image doit être confirmée sur la machine de déploiement. Le wheel et l’application ont toutefois été construits et testés hors Docker.

## 8. Procédure de retour à la version précédente

1. Arrêter l’application sans supprimer les volumes:

```bash
docker compose down
```

2. Conserver une copie du dossier actuel et du volume de données.

3. Extraire:

`rollback/AxioLoad_0.4.0_original.zip`

4. Replacer le contenu de la version 0.4.0 dans le répertoire de l’application.

5. Reconstruire et redémarrer:

```bash
docker compose build --no-cache
docker compose up -d --force-recreate
```

Ne pas utiliser `docker compose down -v`, car cette option supprimerait les données persistantes.

Les préférences 0.5.0 présentes dans le navigateur sont ignorées par la version 0.4.0. Elles peuvent être supprimées depuis les outils du navigateur si nécessaire.

## 9. Conclusion de recette

La version 0.5.0 satisfait le périmètre demandé tout en maintenant le moteur et les données existants. Les limites relatives à l’authentification et au stockage de secrets sont explicites et isolées afin de ne pas transformer une amélioration d’interface en chantier de sécurité global non validé.

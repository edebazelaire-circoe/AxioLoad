# Revue technique et sécurité du module Facturation électronique

Date de revue : 2026-08-09

## Conclusion

Le module est **apte à un pilote fonctionnel interne** après passage complet du CI et validation du déploiement HTTPS.

Il n’est **pas encore qualifié pour une mise en production réglementaire Factur-X**. Le flux métier, l’isolation des données, l’import documentaire, le préremplissage, les permissions et la validation humaine sont opérationnels, mais le fichier produit par `build_facturx_xml()` reste un XML interne simplifié. La qualification réglementaire exige encore un XML CII conforme, sa validation XSD/Schematron et son incorporation dans un PDF/A-3 conforme Factur-X.

## Architecture vérifiée

### Un seul flux de facturation

- les factures sont persistées uniquement par `FacturXRepository` ;
- les tiers sont persistés dans la table `invoice_parties` du même tenant ;
- l’interface utilise uniquement `/api/facturx/*` pour les données Factur-X ;
- aucune facture n’est stockée dans `localStorage` ou `sessionStorage` ;
- l’historique réutilise la même liste `/api/facturx/invoices` et ne crée aucun stockage parallèle.

### Connexion à l’intelligence artificielle

Factur-X réutilise le même mécanisme que le contrôle documentaire :

- `DocumentControlRepository` porte la configuration IA de l’entreprise ;
- `get_connection_config()` de `company_ai_dual_mode` est utilisé par la route d’extraction Factur-X ;
- aucun second stockage de clé API n’est créé dans le module Factur-X ;
- le mode passerelle d’entreprise et le mode clé API OpenAI sont donc partagés entre les deux modules ;
- les requêtes d’extraction utilisent `store: false`.

## Contrôles de sécurité validés

### Isolation multi-tenant

Chaque entreprise possède son fichier SQLite de tenant. Les routes Factur-X résolvent le tenant depuis le contexte de session, puis `FacturXRepository` ouvre uniquement le chemin correspondant. Un test dédié vérifie qu’un tiers et une facture créés dans un tenant ne sont pas visibles dans un autre.

### Permissions

Le module distingue :

- `facturx.view` ;
- `facturx.edit` ;
- `facturx.validate` ;
- `facturx.export`.

Les routes d’écriture passent par le contrôle de permission avec `write=True`. L’export XML est refusé tant qu’une validation humaine n’a pas été enregistrée.

### Import PDF et image

Le pipeline documentaire partagé impose :

- PDF, JPG, JPEG ou PNG uniquement ;
- 10 Mo maximum ;
- 20 pages maximum pour un PDF ;
- ouverture réelle du PDF ou de l’image afin de rejeter les fichiers illisibles ;
- compression et conversion des images avant envoi ;
- aucun enregistrement du binaire source dans les tables Factur-X.

### Secrets IA

En mode OpenAI direct, la clé est chiffrée avec Fernet à partir de `PLO_DOCUMENT_SECRET_KEY`. La clé en clair n’est chargée que lorsque l’appel fournisseur doit être effectué.

La variable `PLO_DOCUMENT_SECRET_KEY` doit être fournie par un gestionnaire de secrets en production et ne doit jamais être stockée dans le dépôt.

### Passerelle IA d’entreprise

Le mécanisme existant protège contre les destinations réseau dangereuses : HTTPS obligatoire par défaut, refus des adresses locales/privées, nouvelle vérification DNS avant l’appel, taille maximale de réponse et temps limite réseau.

### Prompt injection documentaire

Le prompt d’extraction précise que le document est une donnée non fiable et interdit l’exécution d’instructions contenues dans le document. La sortie OpenAI est contrainte par un JSON Schema strict.

### Sécurité navigateur ajoutée lors de cette revue

La revue ajoute un middleware commun :

- `Secure` ajouté aux cookies de session lorsque la requête est servie en HTTPS ;
- `HttpOnly` et `SameSite=Lax` existants conservés ;
- refus d’une requête d’écriture authentifiée lorsque le navigateur fournit un `Origin` différent du host LogiPilot ;
- `X-Content-Type-Options: nosniff` ;
- `X-Frame-Options: DENY` ;
- `Referrer-Policy: same-origin` ;
- `Permissions-Policy` restrictive ;
- HSTS activé en HTTPS.

## Contrôles fonctionnels ajoutés

Le test navigateur réel vérifie maintenant :

1. les quatre espaces Base de données, Optimisation, Contrôle documentaire et Facturation électronique sont alignés sur une seule ligne sur un écran de 1500 px ;
2. Facturation électronique ouvre la vue **Transformation des factures** ;
3. le second onglet **Historique** utilise le même panneau Factur-X et la même liste de factures ;
4. le retour vers Transformation réaffiche le formulaire ;
5. une actualisation complète ne renvoie pas vers le transport ;
6. aucune erreur JavaScript n’est remontée pendant le parcours.

## Couverture du besoin fonctionnel initial

La revue ne considère pas le cahier des charges comme intégralement achevé. Les fonctions suivantes sont déjà opérationnelles :

- création manuelle d’une facture ;
- import PDF/image avec extraction IA et préremplissage ;
- factures émises ou reçues, facture/avoir/acompte et autoliquidation ;
- référentiel clients/fournisseurs réutilisable ;
- fusion automatique sur identifiant fiable ;
- contrôle des lignes, de la TVA et des totaux ;
- proposition automatique de profil ;
- validation humaine avant export ;
- historique dans le même flux de données ;
- XML intermédiaire et rapport de conformité.

Les éléments convenus mais **pas encore réalisés** sont :

- import CSV/Excel du référentiel clients/fournisseurs ;
- import CSV/Excel et copier-coller tableur pour les lignes de facture ;
- interrogation SIRENE/VIES pour compléter ou vérifier un tiers ;
- proposition de rapprochement avec confirmation humaine lorsque les identifiants ne permettent pas une fusion certaine ;
- séquences de numérotation configurables par type de document, établissement ou activité ;
- modèles réutilisables et duplication d’une facture existante ;
- cycle de conservation configurable par entreprise ;
- modification d’une facture validée réservée à l’administrateur principal avec invalidation automatique de la validation précédente ;
- modèle PDF HTML/CSS personnalisable géré par l’administrateur technique ;
- export PDF lisible distinct ;
- véritable export hybride Factur-X PDF/A-3 + CII ;
- comportement configurable de génération automatique des brouillons lorsque les contrôles sont conformes.

Ces écarts ne bloquent pas un pilote ciblé sur **PDF/image → préremplissage → contrôle → validation → historique**, mais ils doivent rester dans la feuille de route avant de qualifier la solution de complète au regard du besoin initial.

## Points restant à traiter avant production réglementaire

### P0 - Conformité Factur-X réelle

Le générateur actuel ne doit pas être présenté comme un générateur Factur-X réglementaire final. Il manque :

- XML CII avec namespaces et règles officielles ;
- profils Factur-X réellement conformes ;
- validation XSD ;
- validation Schematron ;
- PDF/A-3 ;
- incorporation du fichier `factur-x.xml` dans le PDF ;
- contrôle final par un validateur Factur-X indépendant.

**Statut : bloquant production réglementaire.**

### P1 - Politique de conservation et archivage

Le choix métier actuel supprime le document source après extraction et conserve les données structurées. La durée de conservation configurable par entreprise prévue dans le besoin initial n’est pas encore appliquée au cycle de vie des factures Factur-X.

Pour les factures reçues et les pièces ayant une valeur probatoire, la politique de suppression du document original doit être validée avec les obligations comptables et fiscales applicables avant production.

### P1 - Journal d’audit Factur-X

La validation humaine est historisée, mais le journal métier doit encore couvrir de manière homogène : création, modification, extraction IA, validation, invalidation après modification, export et désactivation d’un tiers.

### P1 - Limitation de débit

Aucun mécanisme applicatif de rate limiting n’a été identifié sur l’authentification et l’extraction IA. Un reverse proxy peut fournir cette protection, mais elle doit être explicitement configurée et testée avant exposition publique.

### P2 - Content Security Policy

Les protections navigateur sont renforcées, mais aucune CSP stricte n’est encore appliquée. Une CSP avec nonces ou hashes nécessite d’abord de supprimer ou qualifier les scripts/styles inline existants.

### P2 - Rotation de la clé de chiffrement

Le chiffrement des clés IA est correct, mais aucune procédure automatisée de rotation de `PLO_DOCUMENT_SECRET_KEY` n’est encore fournie. Une procédure d’exploitation et de sauvegarde est nécessaire.

## Décision de mise en service

### Pilote interne

**GO sous réserve du CI entièrement vert.**

Conditions : HTTPS sur l’environnement cible, secret de chiffrement fourni hors dépôt, sauvegardes des bases tenant et droits Factur-X correctement attribués.

### Production Internet

**GO conditionnel** après ajout ou configuration vérifiée d’un rate limiting, revue CSP, supervision et tests de restauration.

### Production réglementaire Factur-X

**NO-GO actuellement** tant que le P0 de conformité Factur-X réelle n’est pas achevé et validé par un validateur indépendant.

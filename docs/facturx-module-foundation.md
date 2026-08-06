# Module de facturation électronique Factur-X

## Périmètre validé

Le module traite les factures émises et reçues, pour les cas B2B, B2C, internationaux, les avoirs, les acomptes et l’autoliquidation.

La première version fonctionne uniquement par export. Elle ne transmet aucune facture à une plateforme agréée.

## Parcours cible

1. Import PDF, JPG ou PNG, prise de photo ou création manuelle.
2. Extraction par la connexion IA déjà configurée par l’entreprise.
3. Suppression du document source immédiatement après extraction.
4. Normalisation dans le modèle interne de facture.
5. Rapprochement avec la base des clients et fournisseurs.
6. Complément depuis la base interne, la saisie manuelle et des référentiels publics officiels.
7. Contrôle des lignes, taux, montants HT, TVA et TTC.
8. Validation humaine obligatoire.
9. Export du PDF lisible, du XML, du document Factur-X et du rapport de conformité.

## Décisions métier

- mode manuel ou automatisé configurable par entreprise ;
- profil Factur-X choisi automatiquement selon le contenu ;
- validation humaine toujours obligatoire avant export ;
- création des tiers par saisie, facture, import CSV/Excel et future synchronisation ERP ;
- fusion automatique uniquement sur identifiant fiable, notamment SIREN, SIRET ou TVA ;
- incohérences de montants bloquantes ;
- durée de conservation configurable avec une valeur par défaut réglementaire ;
- tous les utilisateurs autorisés peuvent valider ;
- après validation, seul l’administrateur principal peut modifier, avec annulation de la validation ;
- séquences de numérotation configurables selon document, établissement ou activité ;
- création manuelle, duplication et modèle réutilisable ;
- un modèle de facture par entreprise ;
- modèle HTML/CSS administré uniquement par un administrateur technique ;
- lignes éditables avec import CSV/Excel, copier-coller et contrôle automatique.

## Contenu de cette PR

Cette PR introduit le socle backend :

- permissions dédiées ;
- tables isolées par base d’entreprise ;
- brouillons de factures entrantes et sortantes ;
- validation déterministe des totaux ;
- sélection initiale du profil ;
- validation humaine ;
- journal d’événements ;
- export XML structuré et rapport JSON ;
- tests unitaires et d’intégration des routes.

## Limites explicites

Le PDF/A-3 avec XML embarqué, la validation officielle XSD/Schematron, l’extraction IA depuis un document, la base complète des tiers, l’interface utilisateur et les imports CSV/Excel feront l’objet de PR suivantes. Le XML de cette PR constitue un contrat interne de génération, pas encore un fichier certifié conforme Factur-X.

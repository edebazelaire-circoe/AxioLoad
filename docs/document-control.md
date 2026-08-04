# Contrôle documentaire AxioLoad

## Connexion à l’intelligence artificielle

Le responsable principal de l’entreprise choisit l’un des deux modes de connexion dans **Paramètres** :

1. **Passerelle de l’entreprise** : AxioLoad appelle un endpoint HTTPS administré par le client. La passerelle conserve la maîtrise de l’authentification, du fournisseur, du modèle, des quotas et de la facturation.
2. **Clé API OpenAI** : AxioLoad appelle directement l’API OpenAI avec une clé appartenant au client. La clé est chiffrée avant son enregistrement et n’est jamais réaffichée dans l’interface.

La configuration est accessible uniquement au responsable principal de l’entreprise. Les utilisateurs standards voient seulement si le contrôle documentaire est disponible. Le superadministrateur AxioLoad ne peut pas enregistrer ou remplacer la connexion pour le compte du client.

Le passage d’un mode à l’autre supprime les identifiants devenus inactifs. Une clé OpenAI n’est donc pas conservée en arrière-plan lorsqu’une passerelle d’entreprise est activée.

## Modèles OpenAI autorisés

La connexion directe n’accepte pas un nom de modèle libre. Le responsable choisit dans une liste contrôlée par AxioLoad :

| Modèle | Usage recommandé |
|---|---|
| `gpt-5-mini` | Modèle par défaut, meilleur équilibre entre qualité, vitesse et coût |
| `gpt-5.1` | Dossiers complexes et documents difficiles à lire |
| `gpt-5` | Modèle généraliste haut de gamme conservé pour compatibilité |
| `gpt-4.1` | Analyse structurée fiable |
| `gpt-4.1-mini` | Contrôles courants avec un coût réduit |
| `gpt-4o` | Compatibilité multimodale |
| `gpt-4o-mini` | Contrôles simples à faible coût |

Tout autre identifiant de modèle est refusé par l’API AxioLoad, même s’il est envoyé manuellement. Cette liste volontairement fermée évite l’utilisation accidentelle d’un modèle non testé, obsolète ou inadapté au traitement de documents.

## Mode passerelle d’entreprise

AxioLoad effectue une requête `POST` vers l’endpoint configuré avec le contrat :

```text
axioload.document-control.v1
```

Deux actions sont prévues :

- `healthcheck` pour tester l’accessibilité de la passerelle ;
- `analyze` pour transmettre les deux documents, les prompts applicables et le schéma JSON attendu.

La passerelle du client prend en charge :

- l’authentification auprès du fournisseur d’IA ;
- le choix du fournisseur et du modèle ;
- les quotas, la facturation et les limites de consommation ;
- les règles de conservation appliquées par le fournisseur ;
- la conversion de la réponse du fournisseur vers le schéma structuré AxioLoad.

AxioLoad n’ajoute aucun en-tête `Authorization` et n’attend aucune clé dans l’URL. Les paramètres de requête, fragments et identifiants intégrés à l’URL sont refusés. HTTPS est obligatoire. Les endpoints locaux ou privés sont bloqués par défaut afin de réduire les risques de requêtes serveur non autorisées. Ils ne peuvent être activés que par une configuration explicite de l’hébergement :

```bash
export PLO_ALLOW_PRIVATE_AI_ENDPOINTS=1
```

L’utilisation de HTTP est désactivée par défaut et réservée aux environnements techniques explicitement configurés :

```bash
export PLO_ALLOW_INSECURE_AI_ENDPOINTS=1
```

### Exemple de requête d’analyse vers la passerelle

```json
{
  "contract_version": "axioload.document-control.v1",
  "action": "analyze",
  "request_id": "identifiant-unique",
  "store": false,
  "system_prompt": "prompt AxioLoad versionné",
  "instruction": "consignes du contrôle",
  "response_schema": {},
  "documents": [
    {
      "side": "left",
      "filename": "document-1.pdf",
      "media_type": "application/pdf",
      "page_count": 2,
      "content_base64": "..."
    },
    {
      "side": "right",
      "filename": "document-2.jpg",
      "media_type": "image/jpeg",
      "page_count": 1,
      "content_base64": "..."
    }
  ]
}
```

La passerelle peut renvoyer directement l’objet de comparaison ou l’encapsuler dans une propriété `result`.

## Mode clé API OpenAI

Le serveur doit disposer d’une clé de chiffrement stable :

```bash
export PLO_DOCUMENT_SECRET_KEY="une-valeur-secrete-longue-et-stable"
```

Cette valeur ne doit jamais être commitée. Elle sert uniquement à chiffrer et déchiffrer les clés API des entreprises.

Lors de l’enregistrement, le responsable renseigne :

- la clé API OpenAI ;
- l’un des modèles autorisés ;
- la confirmation qu’il a vérifié la politique de conservation applicable à son compte.

La clé complète n’est jamais renvoyée par l’API AxioLoad. Seuls les quatre derniers caractères sont affichés pour permettre au responsable d’identifier la clé utilisée. Les appels d’analyse passent par l’API Responses avec `store: false` et un schéma JSON strict.

Le bouton **Tester la connexion** vérifie la validité de la clé et l’accès au modèle sélectionné sans transmettre de document.

## Sécurité documentaire

- Formats acceptés : PDF, JPG, JPEG et PNG.
- Taille maximale : 10 Mo par document.
- PDF : 20 pages maximum.
- Les images sont redimensionnées et compressées avant l’appel distant.
- Les octets des documents restent limités à la requête en cours et ne sont jamais écrits dans les bases AxioLoad.
- Les noms de fichiers ne sont pas enregistrés dans l’historique.
- Les exports PDF et Excel sont générés à la volée et ne sont pas stockés.
- L’historique conserve seulement les écarts, les corrections, les commentaires, la consigne ponctuelle, le mode de connexion et le modèle utilisé.

## Prompts

Le prompt système AxioLoad est verrouillé dans le code et versionné. Il définit l’objectif, les règles de lecture littérale, la protection contre les instructions présentes dans les documents et le format structuré attendu.

Le responsable principal de l’entreprise peut ajouter un complément métier imposé pour chaque couple de types de documents. Les utilisateurs ne peuvent pas modifier ce socle ni choisir un autre complément, mais peuvent ajouter une consigne ponctuelle qui reste tracée dans l’historique.

## Accès

Les permissions suivantes sont ajoutées :

- `document_control.view` ;
- `document_control.run` ;
- `document_control.history` ;
- `document_control.export`.

Un utilisateur ne voit que les contrôles qu’il a réalisés. Le responsable principal voit l’ensemble des contrôles de son entreprise et dispose seul de la configuration de la connexion IA.

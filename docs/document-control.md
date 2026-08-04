# Contrôle documentaire AxioLoad

## Connexion à l’intelligence artificielle

AxioLoad ne reçoit et ne conserve plus de clé API appartenant au client. Le responsable de l’entreprise renseigne uniquement, dans **Paramètres**, l’adresse HTTPS d’une passerelle IA administrée par son entreprise.

Le texte présenté dans l’interface est le suivant :

> AxioLoad n’enregistre aucune clé d’accès à votre fournisseur d’IA. Seul le responsable de l’entreprise peut consulter, modifier ou supprimer cet endpoint. La passerelle de votre entreprise conserve la maîtrise de l’authentification, du modèle, des quotas et de la facturation.

L’adresse complète de l’endpoint est accessible uniquement au responsable principal de l’entreprise. Les utilisateurs standards savent seulement si le contrôle documentaire est disponible. Le superadministrateur AxioLoad ne peut plus enregistrer de fournisseur, de modèle ou de clé pour le compte du client.

Les anciennes clés fournisseur éventuellement présentes dans une base antérieure sont supprimées lors de la migration vers l’architecture endpoint-only.

## Contrat de la passerelle

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

## Exemple de requête d’analyse

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

## Sécurité documentaire

- Formats acceptés : PDF, JPG, JPEG et PNG.
- Taille maximale : 10 Mo par document.
- PDF : 20 pages maximum.
- Les images sont redimensionnées et compressées avant l’appel distant.
- Les octets des documents restent limités à la requête en cours et ne sont jamais écrits dans les bases AxioLoad.
- Les noms de fichiers ne sont pas enregistrés dans l’historique.
- Les exports PDF et Excel sont générés à la volée et ne sont pas stockés.
- L’historique conserve seulement les écarts, les corrections, les commentaires, la consigne ponctuelle et les versions de prompts.

## Prompts

Le prompt système AxioLoad est verrouillé dans le code et versionné. Il définit l’objectif, les règles de lecture littérale, la protection contre les instructions présentes dans les documents et le format structuré attendu.

Le responsable principal de l’entreprise peut ajouter un complément métier imposé pour chaque couple de types de documents. Les utilisateurs ne peuvent pas modifier ce socle ni choisir un autre complément, mais peuvent ajouter une consigne ponctuelle qui reste tracée dans l’historique.

## Accès

Les permissions suivantes sont ajoutées :

- `document_control.view` ;
- `document_control.run` ;
- `document_control.history` ;
- `document_control.export`.

Un utilisateur ne voit que les contrôles qu’il a réalisés. Le responsable principal voit l’ensemble des contrôles de son entreprise et dispose seul de la configuration de la passerelle IA.

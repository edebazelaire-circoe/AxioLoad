# Contrôle documentaire AxioLoad

## Activation

Le module utilise une clé de chiffrement serveur distincte des clés API des entreprises :

```bash
export PLO_DOCUMENT_SECRET_KEY="une-valeur-secrete-longue-et-stable"
```

Cette valeur doit rester stable entre les redémarrages et ne doit jamais être commitée. Elle chiffre les clés des fournisseurs IA enregistrées dans la fiche de chaque entreprise.

Le superadministrateur configure ensuite, dans l'onglet **API** de la fiche entreprise :

- le fournisseur ;
- le modèle ;
- la clé API propre à l'entreprise ;
- la durée de conservation de l'historique, de 1 à 12 mois, 6 mois par défaut ;
- la confirmation que le contrat ou compte fournisseur respecte l'exigence de non-conservation.

La V1 exécutable utilise OpenAI via l'API Responses avec `store: false`. L'utilisation sans conservation supplémentaire dépend aussi des paramètres et engagements contractuels du compte fournisseur ; AxioLoad exige donc une confirmation explicite avant l'activation.

## Sécurité documentaire

- Formats acceptés : PDF, JPG, JPEG et PNG.
- Taille maximale : 10 Mo par document.
- PDF : 20 pages maximum.
- Les images sont redimensionnées et compressées avant l'appel distant.
- Les octets des documents restent limités à la requête en cours et ne sont jamais écrits dans les bases AxioLoad.
- Les noms de fichiers ne sont pas enregistrés dans l'historique.
- Les exports PDF et Excel sont générés à la volée et ne sont pas stockés.
- L'historique conserve seulement les écarts, les corrections, les commentaires, la consigne ponctuelle, le modèle et les versions de prompts.

## Prompts

Le prompt système AxioLoad est verrouillé dans le code et versionné. Il définit l'objectif, les règles de lecture littérale, la protection contre les instructions présentes dans les documents et le format structuré attendu.

L'administrateur principal de l'entreprise peut ajouter un complément métier imposé pour chaque couple de types de documents. Les utilisateurs ne peuvent pas modifier ce socle ni choisir un autre complément, mais peuvent ajouter une consigne ponctuelle qui reste tracée dans l'historique.

## Accès

Les permissions suivantes sont ajoutées :

- `document_control.view` ;
- `document_control.run` ;
- `document_control.history` ;
- `document_control.export`.

Un utilisateur ne voit que les contrôles qu'il a réalisés. L'administrateur principal voit l'ensemble des contrôles de son entreprise.

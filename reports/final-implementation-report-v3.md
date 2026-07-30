# Pallet Loading Optimizer V3 - rapport de correction

## Corrections principales

1. L'interface locale ne demande plus de clé API. Les écrans Véhicules, Données, Résultats, Historique, imports et exports utilisent le tenant local créé automatiquement.
2. L'endpoint navigateur est désormais `/local/optimize`. L'ancien `/demo/optimize` reste un alias de compatibilité pour éviter qu'un cache navigateur V2 ne bloque l'application.
3. Les clés API restent uniquement sur l'endpoint d'intégration facultatif `/v1/optimizations`.
4. Les huit stratégies du portefeuille de placement sont exécutées et validées séparément avant agrégation et classement.
5. Les résultats sont rejetés s'ils dépassent la longueur, la largeur, la hauteur, l'ouverture ou la charge utile du véhicule, ou s'ils créent une collision.

## Recette réalisée

- 36 tests automatisés réussis.
- Test séparé de chacune des huit stratégies de placement sur le cas signalé: une caisse 1200 x 800 mm et un cylindre 1200 x 1000 mm dans le porteur 20 m3.
- Test de l'API locale sans clé avec PLO_DEMO_MODE=0.
- Test de création et modification d'un véhicule sans clé API.
- Test prouvant qu'une largeur intérieure modifiée à 1500 mm borne effectivement toutes les positions calculées.
- Smoke test de bout en bout réussi.
- Test navigateur Playwright réussi: édition du véhicule, optimisation de trois palettes et affichage des résultats.
- Compilation Python réussie.
- Construction du paquet wheel réussie.

## Limite de la recette dans cet environnement

Le binaire Docker n'est pas installé dans l'environnement d'exécution utilisé pour cette correction. Le `Dockerfile` et le `docker-compose.yml` ont été contrôlés statiquement, mais l'image Docker n'a pas pu être construite ici. La recette applicative complète a été effectuée directement avec la même application FastAPI et les mêmes sources utilisées par l'image.

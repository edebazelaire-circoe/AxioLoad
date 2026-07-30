# Décisions et écarts V3

## Décisions

- Le catalogue véhicule n’est plus codé uniquement en dur: il est persistant et modifiable depuis l’écran 0.
- Les dimensions intérieures configurées sont injectées dans la normalisation et utilisées directement par le moteur.
- La longueur réellement occupée précède désormais le métrage linéaire dans le classement entre plans utilisant le même nombre de véhicules.
- Le moteur combine MaxRects et points extrêmes afin de réduire les faux échecs d’une heuristique unique.
- Une prévalidation explique précisément lorsqu’un objet dépasse les dimensions, l’ouverture, la hauteur, la charge utile ou la capacité totale disponible.
- Les messages génériques sans diagnostic ont été supprimés de l’interface.

## Écarts documentés

- Le moteur reste heuristique et ne fournit pas de certificat d’optimalité mathématique.
- Le modèle d’essieux est statique à deux appuis et ne tient pas compte du poids à vide complet, de la suspension ou des règles nationales.
- Le contrôle LIFO est géométrique par couloir; il ne simule pas le chemin d’un chariot ou d’un transpalette.
- Aucun gerbage n’est réalisé dans cette version.
- Les modèles de démonstration doivent être remplacés ou validés avec les caractéristiques réelles des véhicules.

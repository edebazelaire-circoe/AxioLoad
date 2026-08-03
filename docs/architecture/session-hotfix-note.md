# Correctif de session 0.22.1

Ce correctif garantit qu'un utilisateur authentifié conserve toujours un bouton de déconnexion, même lorsque les contrôles de la barre supérieure sont injectés dans un ordre différent.

Le mécanisme utilise des tentatives bornées au démarrage et ne réintroduit aucun observateur global permanent.

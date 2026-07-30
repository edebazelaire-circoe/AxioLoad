# Contrôle de gabarit des itinéraires

AxioLoad contrôle la faisabilité physique des marchandises présentes dans le véhicule à chaque état de charge : dimensions intérieures, ouverture, charge utile, essieux, LIFO et gerbage.

Le fond routier public OSRM est appelé avec un profil automobile générique. Il ne garantit donc pas les interdictions liées à la hauteur, à la largeur, à la longueur ou au tonnage du véhicule. L’interface affiche cette limite au lieu de présenter ce contrôle comme acquis. Une instance de routage poids lourd dédiée sera nécessaire pour rendre ce second niveau bloquant.

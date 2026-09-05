"""Point d'entree UNIQUE pour la chaine de connexion PostgreSQL.

Port 5433, pas 5432 : un PostgreSQL natif Windows (sans rapport avec ce
projet, jamais installe par nous) occupe le port 5432 sur cette machine, en
dual-stack (IPv4 ET IPv6) -- toute connexion vers 5432 y atterrissait
silencieusement, jamais vers notre conteneur Docker. D'ou l'echec
d'authentification trompeur observe alors qu'identifiants et conteneur
etaient corrects. Le conteneur nutrition-kb-pg (le vrai, avec les donnees)
tourne maintenant sur -p 5433:5432.

Cette constante etait dupliquee dans 5 fichiers avant consolidation ici :
un seul endroit a corriger si le port ou les identifiants changent encore --
sinon un fichier oublie reste silencieusement sur l'ancienne valeur.
"""

import os

DEFAULT_DSN = "postgresql://nutrition:nutrition@localhost:5433/nutrition_kb"

DSN = os.environ.get("NUTRITION_KB_DSN", DEFAULT_DSN)

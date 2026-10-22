# Analyse ponctuelle des règles de sortie

Données jusqu'au 2026-10-21. Début du backtest : 2011-03-15. Frais : 0,10 % par transaction. Seuil de conservation du site : rang 50, 20 lignes.

Protocole fixé le 22/10/2026 avant exécution (voir l'en-tête d'analyse_sorties.py). La période réservée étant déjà révélée, ces résultats ne valent pas validation : une variante « candidate » doit encore passer 12 mois de suivi en parallèle.

## 1. Vérification

- v1 site : écart relatif max 0.0e+00, 446 ventes contre 446, décisions différentes de review_decision : 0
- v1 decale : écart relatif max 0.0e+00, 462 ventes contre 462, décisions différentes de review_decision : 0
- v2 site : écart relatif max 0.0e+00, 469 ventes contre 469, décisions différentes de review_decision : 0
- v2 decale : écart relatif max 0.0e+00, 532 ventes contre 532, décisions différentes de review_decision : 0
- v3 site : écart relatif max 0.0e+00, 412 ventes contre 412, décisions différentes de review_decision : 0
- v3 decale : écart relatif max 0.0e+00, 451 ventes contre 451, décisions différentes de review_decision : 0
- durée (s) : 164

## 2. Que rapportent les ventes du site ?

Rendement après la revue, en écart au S&P 500 équipondéré, moyenne par revue (calendrier du site, règle du site).

| Modèle | Horizon | Vendus | Achetés | Conservés | Achetés − vendus | t | Revues où les achats battent les ventes |
|---|---|---|---|---|---|---|---|
| V1 | 63 séances | −0,3 % | +0,8 % | −0,7 % | +1,1 % | 1,3 | 57 % |
| V1 | 126 séances | +0,0 % | +1,6 % | −0,8 % | +1,5 % | 1,4 | 58 % |
| V1 | 252 séances | +0,3 % | +0,6 % | −1,1 % | +0,3 % | 0,2 | 48 % |
| V2 | 63 séances | −0,2 % | +1,6 % | −0,0 % | +1,9 % | 1,8 | 52 % |
| V2 | 126 séances | +0,4 % | +1,6 % | +0,3 % | +1,3 % | 0,9 | 60 % |
| V2 | 252 séances | −0,7 % | +0,9 % | +0,5 % | +1,6 % | 0,8 | 55 % |
| V3 | 63 séances | −0,6 % | +0,6 % | −0,5 % | +1,1 % | 1,2 | 59 % |
| V3 | 126 séances | +0,1 % | +0,6 % | −0,2 % | +0,6 % | 0,5 | 50 % |
| V3 | 252 séances | +0,2 % | +1,2 % | −0,4 % | +1,0 % | 0,6 | 57 % |

Titres vendus selon leur rang le jour de la vente (écart moyen à l'équipondéré sur les 6 et 12 mois suivants) :

| Modèle | Rang à la vente | Ventes | 6 mois | 12 mois | Battent l'équipondéré à 12 mois |
|---|---|---|---|---|---|
| V1 | 51-75 | 144 | +0,3 % | −0,7 % | 48 % |
| V1 | 76-100 | 104 | +1,6 % | +2,6 % | 55 % |
| V1 | 101-150 | 116 | −0,8 % | −0,3 % | 48 % |
| V1 | > 150 | 79 | −2,2 % | −4,1 % | 38 % |
| V1 | plus éligible | 3 | −12,3 % | −6,9 % | – |
| V2 | 51-75 | 147 | +1,0 % | +0,1 % | 52 % |
| V2 | 76-100 | 109 | +0,5 % | −2,5 % | 43 % |
| V2 | 101-150 | 123 | +0,6 % | −2,2 % | 43 % |
| V2 | > 150 | 86 | −1,2 % | −0,5 % | 45 % |
| V2 | plus éligible | 4 | −10,6 % | −11,9 % | – |
| V3 | 51-75 | 148 | −0,4 % | −1,0 % | 42 % |
| V3 | 76-100 | 105 | +1,6 % | +1,5 % | 51 % |
| V3 | 101-150 | 92 | +0,9 % | −0,6 % | 49 % |
| V3 | > 150 | 64 | −0,7 % | +0,9 % | 48 % |
| V3 | plus éligible | 3 | −1,2 % | +3,3 % | – |

- V1 : 23 % des titres vendus sont de retour dans le top 50 à la revue suivante, 8 % dans le top 20.
- V2 : 19 % des titres vendus sont de retour dans le top 50 à la revue suivante, 8 % dans le top 20.
- V3 : 23 % des titres vendus sont de retour dans le top 50 à la revue suivante, 7 % dans le top 20.

## 3. Variantes : écart à la référence

Moyenne sur 6 cellules (3 modèles x 2 calendriers). Écarts de rendement annualisé net de frais, en points ; perte maximale : un écart positif est une amélioration.

| Variante | Famille | Cellules gagnantes | Totale | 2011-2015 | 2016-2020 | 2021+ | Perte max | Sharpe | Ventes/an | Durée médiane (j) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| seuil_x1.5 | rendement | 4/6 | −0,15 % | +0,13 % | −0,77 % | +0,12 % | +1,0 % | −0,01 | 22,5 | 259 | rejetée |
| seuil_x2 | rendement | 2/6 | −0,23 % | +0,25 % | −0,34 % | −0,61 % | +0,0 % | −0,01 | 17,8 | 350 | rejetée |
| seuil_x3 | rendement | 4/6 | +0,44 % | +0,78 % | +2,52 % | −1,72 % | +1,4 % | 0,03 | 11,3 | 428 | rejetée |
| duree_6m | rendement | 6/6 | +0,54 % | +0,17 % | +0,45 % | +0,92 % | +1,3 % | 0,02 | 23,9 | 250 | candidate |
| duree_12m | rendement | 3/6 | −0,10 % | −0,07 % | +0,24 % | −0,46 % | +0,3 % | −0,01 | 19,0 | 365 | rejetée |
| rang_lisse | rendement | 5/6 | +0,41 % | −1,16 % | +0,17 % | +1,94 % | +1,9 % | 0,02 | 24,8 | 244 | rejetée |
| bande | rendement | 2/6 | −0,07 % | −0,04 % | +0,15 % | −0,27 % | −0,1 % | −0,01 | 29,7 | 197 | rejetée |
| sans_reequilibrage | rendement | 3/6 | +0,03 % | −0,04 % | +0,49 % | −0,29 % | −0,1 % | −0,00 | 29,7 | 197 | rejetée |
| stop_suiveur_25 | risque | 1/6 | −0,72 % | +0,40 % | −0,20 % | −2,11 % | −0,9 % | −0,03 | 33,2 | 178 | rejetée |
| stop_relatif_20 | risque | 2/6 | −0,38 % | +0,04 % | +0,49 % | −1,45 % | +0,3 % | −0,02 | 31,3 | 181 | rejetée |
| combinaison | rendement | 4/6 | +0,07 % | +0,84 % | +0,66 % | −1,14 % | +0,3 % | 0,00 | 16,7 | 355 | rejetée |
| filtre_marche | risque | 0/6 | −4,79 % | −4,28 % | −4,34 % | −5,67 % | +7,1 % | −0,19 | 29,7 | 197 | rejetée |

Libellés :

- `reference` : Règle du site : conserver tant que rang <= 50, rééquilibrage à poids égaux à chaque revue
- `seuil_x1.5` : Conserver tant que rang <= 75
- `seuil_x2` : Conserver tant que rang <= 100
- `seuil_x3` : Conserver tant que rang <= 150
- `duree_6m` : Pas de vente sur le rang avant 6 mois de détention, sauf rang > 150
- `duree_12m` : Pas de vente sur le rang avant 12 mois de détention, sauf rang > 150
- `rang_lisse` : Vente sur le rang moyen (3 dernières fins de mois + jour de revue)
- `bande` : Rééquilibrage d'une ligne seulement hors de la bande 0,5x-2x le poids cible
- `sans_reequilibrage` : Lignes conservées jamais rééquilibrées
- `stop_suiveur_25` : Stop suiveur -25 % depuis le plus haut depuis l'achat, remplacement immédiat
- `stop_relatif_20` : Stop relatif : retard de 20 % sur l'équipondéré depuis l'achat, remplacement immédiat
- `combinaison` : Conserver tant que rang <= 100 + 6 mois minimum (sauf rang > 150) + bande 0,5x-2x
- `filtre_marche` : Règle du site + bons du Trésor quand le S&P 500 finit le mois sous sa moyenne 10 mois

## 4. Détail : rendement annualisé, période totale

| Variante | V1 site | V1 decale | V2 site | V2 decale | V3 site | V3 decale |
|---|---|---|---|---|---|---|
| reference | 13,49 % | 12,26 % | 14,41 % | 11,49 % | 12,60 % | 10,74 % |
| seuil_x1.5 | 13,63 % | 12,72 % | 14,51 % | 11,76 % | 10,93 % | 10,53 % |
| seuil_x2 | 13,40 % | 11,94 % | 13,02 % | 11,58 % | 11,53 % | 12,14 % |
| seuil_x3 | 13,44 % | 13,30 % | 12,76 % | 13,26 % | 13,07 % | 11,81 % |
| duree_6m | 13,74 % | 12,65 % | 14,83 % | 12,48 % | 12,79 % | 11,74 % |
| duree_12m | 13,65 % | 11,88 % | 13,04 % | 13,39 % | 11,61 % | 10,82 % |
| rang_lisse | 13,99 % | 12,92 % | 15,22 % | 12,92 % | 11,18 % | 11,20 % |
| bande | 13,31 % | 11,93 % | 14,26 % | 11,71 % | 12,48 % | 10,86 % |
| sans_reequilibrage | 13,31 % | 11,88 % | 14,61 % | 12,02 % | 12,48 % | 10,86 % |
| stop_suiveur_25 | 12,11 % | 11,83 % | 12,78 % | 11,65 % | 11,79 % | 10,51 % |
| stop_relatif_20 | 13,13 % | 11,95 % | 13,35 % | 11,95 % | 11,46 % | 10,88 % |
| combinaison | 13,61 % | 12,36 % | 13,08 % | 11,79 % | 12,60 % | 11,96 % |
| filtre_marche | 8,09 % | 7,76 % | 8,47 % | 7,02 % | 8,02 % | 6,86 % |

## 5. Chance du calendrier et tranches

Règle du site, même fenêtre pour tous (à partir du 2011-05-16, quand les trois tranches sont investies). Rendement annualisé.

| Calendrier | V1 | V2 | V3 |
|---|---|---|---|
| site [3, 5, 8, 11] | 13,09 % | 14,07 % | 12,17 % |
| décalé [4, 6, 9, 12] | 11,99 % | 11,45 % | 10,54 % |
| tranche seule [1, 4, 7, 10] | 12,06 % | 11,97 % | 11,07 % |
| tranche seule [2, 5, 8, 11] | 11,83 % | 14,02 % | 12,28 % |
| tranche seule [3, 6, 9, 12] | 11,46 % | 12,25 % | 10,64 % |
| 3 tranches (règle du site) | 11,78 % | 12,78 % | 11,34 % |
| 3 tranches + combinaison | 11,52 % | 12,40 % | 11,92 % |

## Limites

- Période réservée déjà révélée : ces écarts sont des indices, pas des preuves.
- Sociétés sans cours Yahoo absentes (biais de survivance, voir l'onglet Données).
- Stops : décision à la clôture, exécution à la clôture suivante ; les écarts d'ouverture et l'élargissement des fourchettes en cas de chute ne sont pas modélisés, ce qui avantage les stops.
- Filtre de marché : appliqué à la courbe (le portefeuille continue de vivre pendant les phases en bons du Trésor) ; rotation approximative.

# Analyse ponctuelle des corrections de V1, V2 et V3

Données jusqu'au 2026-11-03. Mesure en 3 tranches à partir du 2011-05-16 (les trois tranches investies). Frais : 0,10 % par transaction.

Protocole fixé le 04/11/2026 avant exécution (en-tête d'analyse_ameliorations.py). Toute la période a déjà été vue : ces résultats sont des indices, pas des preuves.

## 1. Vérification

- Classements du site reproduits (3 dates) : écart max 0.0e+00, colonnes différentes : 0
- V1 au calendrier du site : écart relatif max 0.0e+00, 446 ventes contre 446, décisions différentes de review_decision : 0, rangs identiques à backtest.rank_frame : oui
- V2 au calendrier du site : écart relatif max 0.0e+00, 468 ventes contre 468, décisions différentes de review_decision : 0, rangs identiques à backtest.rank_frame : oui
- V3 au calendrier du site : écart relatif max 0.0e+00, 411 ventes contre 411, décisions différentes de review_decision : 0, rangs identiques à backtest.rank_frame : oui
- Stratégies simulées : 37 (en tranches) et 37 (calendrier du site)
- Durée (s) : 160

## 2. Leviers seuls : écart à la référence (en tranches)

Écarts de rendement annualisé net de frais en points (moyenne des modèles concernés). Perte maximale et volatilité : un écart positif est une amélioration. t : écart de rendement quotidien rapporté à son erreur type, période totale, moyenne des modèles.

| Levier | Famille | Cellules gagnantes | Totale | 2011-2020 | 2021+ | t | Perte max | Volatilité | Sharpe | Écart de suivi S&P | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| vol_secteur | rendement | 5/6 | +1,11 % | +0,79 % | +1,66 % | +1,3 | +0,6 % | −0,7 % | +0,04 | +0,3 % | candidat |
| sans_risque | rendement | 4/6 | +0,87 % | −0,95 % | +4,00 % | +0,8 | −3,9 % | −3,5 % | −0,02 | −1,0 % | rejeté |
| mom_residuel | rendement | 3/6 | −0,71 % | −1,67 % | +0,85 % | −0,8 | −1,0 % | +0,9 % | +0,01 | −0,2 % | rejeté |
| rachats_10 | rendement | 5/6 | +0,76 % | −0,07 % | +2,11 % | +0,8 | −0,6 % | −0,0 % | +0,06 | +0,1 % | candidat |
| sans_croissance | rendement | 1/2 | −0,22 % | +0,17 % | −0,90 % | −0,3 | +0,0 % | +0,5 % | −0,01 | −0,5 % | rejeté |
| resultats_10 | rendement | 2/4 | +0,06 % | +0,09 % | +0,02 % | +0,0 | +0,9 % | +0,3 % | +0,01 | −0,1 % | rejeté |
| duree_6m | rendement | 3/6 | +0,19 % | +0,14 % | +0,26 % | +0,4 | +1,1 % | −0,0 % | +0,01 | +0,2 % | rejeté |
| plafond_3 | risque | 5/6 | +1,31 % | +1,19 % | +1,48 % | +1,6 | +0,9 % | +0,1 % | +0,07 | +0,7 % | candidat |
| poids_vol | risque | 2/6 | −0,49 % | +0,00 % | −1,31 % | −1,0 | +0,5 % | +0,8 % | −0,01 | −0,2 % | rejeté |
| lignes_30 | risque | 4/6 | +0,43 % | +0,62 % | +0,09 % | +0,6 | +0,7 % | +0,3 % | +0,03 | +0,8 % | rejeté |
| donnees | correction | 3/6 | +0,00 % | +0,02 % | −0,03 % | +0,1 | +0,1 % | −0,0 % | −0,00 | +0,0 % | correction (non jugée) |

Détail par modèle, période totale (écart de rendement annualisé, t) :

| Levier | V1 | V2 | V3 |
|---|---|---|---|
| vol_secteur | +1,55 % (t +1,7) | +0,44 % (t +0,8) | +1,34 % (t +1,5) |
| sans_risque | +0,32 % (t +0,5) | +0,86 % (t +1,0) | +1,43 % (t +1,0) |
| mom_residuel | −0,25 % (t −0,3) | −1,07 % (t −1,0) | −0,80 % (t −1,0) |
| rachats_10 | +1,11 % (t +1,2) | +0,68 % (t +0,6) | +0,50 % (t +0,6) |
| sans_croissance | −0,22 % (t −0,3) | – | – |
| resultats_10 | – | −0,26 % (t −0,4) | +0,38 % (t +0,5) |
| duree_6m | +0,49 % (t +1,0) | −0,13 % (t −0,2) | +0,21 % (t +0,5) |
| plafond_3 | +1,96 % (t +2,6) | +0,14 % (t +0,1) | +1,82 % (t +2,3) |
| poids_vol | −0,36 % (t −0,8) | −0,71 % (t −1,2) | −0,39 % (t −0,9) |
| lignes_30 | +0,98 % (t +1,5) | −0,02 % (t −0,2) | +0,32 % (t +0,5) |
| donnees | −0,06 % (t −0,4) | +0,02 % (t +0,3) | +0,04 % (t +0,4) |

## 3. Modèles corrigés (en tranches)

| Stratégie | Rendement/an | Volatilité | Sharpe | Perte max | Bêta | Écart S&P | Écart équipondéré | Écart de suivi S&P | 3 ans battant le S&P | Lignes battant l'équipondéré | Ventes/an |
|---|---|---|---|---|---|---|---|---|---|---|---|
| V1 (référence) | 11,7 % | 16,0 % | 0,67 | −30,7 % | 0,81 | −2,3 % | −0,0 % | 8,4 % | 22 % | 41 % | 87 |
| V2 (référence) | 12,3 % | 18,0 % | 0,65 | −34,0 % | 0,93 | −1,6 % | +0,6 % | 8,5 % | 37 % | 41 % | 96 |
| V3 (référence) | 11,3 % | 15,9 % | 0,65 | −32,0 % | 0,81 | −2,7 % | −0,5 % | 8,5 % | 8 % | 41 % | 84 |
| V1+ | 14,6 % | 16,4 % | 0,82 | −34,5 % | 0,85 | +0,6 % | +2,9 % | 7,7 % | 66 % | 46 % | 57 |
| V2+ | 12,0 % | 16,3 % | 0,68 | −33,3 % | 0,86 | −1,9 % | +0,3 % | 7,5 % | 20 % | 42 % | 86 |
| V3+ | 12,4 % | 17,2 % | 0,67 | −36,0 % | 0,91 | −1,5 % | +0,7 % | 7,4 % | 30 % | 40 % | 71 |
| V4 fusion | 14,2 % | 16,8 % | 0,78 | −38,2 % | 0,87 | +0,3 % | +2,5 % | 7,9 % | 58 % | 45 % | 57 |
| S&P 500 | 14,0 % | 17,2 % | 0,75 | −33,8 % | 1,00 | +0,0 % | +2,3 % | 0,0 % | 0 % | – | 0 |
| S&P 500 équipondéré | 11,7 % | 17,7 % | 0,62 | −39,0 % | 0,98 | −2,3 % | +0,0 % | 5,6 % | 19 % | – | 0 |

Par période (rendement annualisé) :

| Stratégie | 2011-2015 | 2016-2020 | 2011-2020 | 2021+ |
|---|---|---|---|---|
| V1 (référence) | 11,8 % | 11,8 % | 11,6 % | 12,1 % |
| V2 (référence) | 11,0 % | 14,9 % | 12,8 % | 11,8 % |
| V3 (référence) | 12,1 % | 10,6 % | 11,1 % | 11,7 % |
| V1+ | 16,1 % | 14,4 % | 15,0 % | 14,0 % |
| V2+ | 9,5 % | 12,1 % | 10,7 % | 14,5 % |
| V3+ | 14,3 % | 11,3 % | 12,6 % | 12,5 % |
| V4 fusion | 14,0 % | 13,5 % | 13,6 % | 15,4 % |
| S&P 500 | 12,1 % | 15,6 % | 13,7 % | 14,7 % |
| S&P 500 équipondéré | 10,9 % | 13,0 % | 11,8 % | 11,8 % |

Comparaisons (période totale ; écart de rendement annualisé moyen, t) :

| Comparaison | Écart | t |
|---|---|---|
| V1+ − V2+ | +2,27 % | +1,8 |
| V1+ − V3+ | +1,73 % | +1,4 |
| V1+ − V4 fusion | +0,25 % | +0,2 |
| V2+ − V3+ | −0,54 % | −0,5 |
| V2+ − V4 fusion | −2,02 % | −1,4 |
| V3+ − V4 fusion | −1,48 % | −1,1 |
| V1+ − V1 (référence) | +2,63 % | +1,8 |
| V1+ − S&P 500 | +0,40 % | +0,2 |
| V1+ − S&P 500 équipondéré | +2,31 % | +1,2 |
| V2+ − V2 (référence) | −0,57 % | −0,4 |
| V2+ − S&P 500 | −1,87 % | −1,0 |
| V2+ − S&P 500 équipondéré | +0,04 % | +0,0 |
| V3+ − V3 (référence) | +1,29 % | +1,0 |
| V3+ − S&P 500 | −1,33 % | −0,7 |
| V3+ − S&P 500 équipondéré | +0,58 % | +0,3 |
| V4 fusion − V1 (référence) | +2,38 % | +1,4 |
| V4 fusion − V2 (référence) | +1,45 % | +0,7 |
| V4 fusion − V3 (référence) | +2,77 % | +1,7 |
| V4 fusion − S&P 500 | +0,15 % | +0,1 |
| V4 fusion − S&P 500 équipondéré | +2,06 % | +1,2 |
| V1 (référence) − V2 (référence) | −0,93 % | −0,7 |
| V1 (référence) − V3 (référence) | +0,39 % | +0,4 |
| V2 (référence) − V3 (référence) | +1,33 % | +0,9 |

**Verdict (règle 7) :** pas de gagnant net (aucun modèle corrigé ne devance tous les autres de plus de deux erreurs types). Ordre des rendements, pour information : V1+ 14,6 %, V4 fusion 14,2 %, V3+ 12,4 %, V2+ 12,0 %.

Pondérations :

- V1 (référence) : Croissance 25,0 %, Momentum 25,0 %, Qualité 20,0 %, Valorisation 15,0 %, Risque 15,0 %
- V2 (référence) : Momentum 35,0 %, Qualité 25,0 %, Résultats 20,0 %, Valorisation 10,0 %, Risque 10,0 %
- V3 (référence) : Momentum 25,0 %, Qualité 25,0 %, Résultats 20,0 %, Valorisation 15,0 %, Risque 15,0 %
- V1+ : Rachats nets 25,0 %, Momentum 25,0 %, Qualité 20,0 %, Valorisation (données contrôlées) 15,0 %, Risque (au sein du secteur) 15,0 %
- V2+ : Momentum résiduel 39,4 %, Qualité 28,1 %, Valorisation (données contrôlées) 11,2 %, Risque (au sein du secteur) 11,2 %, Résultats 10,0 %
- V3+ : Momentum 34,6 %, Qualité 34,6 %, Valorisation (données contrôlées) 20,8 %, Résultats 10,0 %
- V4 fusion : Résultats (au sein du secteur) 20,0 %, Momentum résiduel (au sein du secteur) 20,0 %, Qualité 20,0 %, Valorisation (données contrôlées) 20,0 %, Rachats nets 20,0 %

## 4. Pouvoir prédictif (corrélation de rang avec le rendement futur)

| Score ou facteur | IC 6 mois | t | IC 12 mois | t | Top 20 battant l'univers à 12 mois (taux de base) | Q1 − Q5 à 12 mois |
|---|---|---|---|---|---|---|
| Score V1 (site) | +0,013 | +0,4 | +0,008 | +0,2 | 44,8 % (46,3 %) | −2,5 % |
| Score V2 (site) | +0,019 | +0,6 | +0,010 | +0,2 | 45,9 % (46,3 %) | −1,3 % |
| Score V3 (site) | +0,018 | +0,6 | +0,013 | +0,3 | 44,7 % (46,3 %) | −1,8 % |
| Score V1+ | +0,027 | +1,2 | +0,030 | +1,1 | 48,8 % (46,4 %) | −0,1 % |
| Score V2+ | +0,018 | +0,7 | +0,003 | +0,1 | 45,9 % (46,3 %) | −1,3 % |
| Score V3+ | +0,020 | +0,8 | +0,009 | +0,3 | 44,5 % (46,3 %) | +0,0 % |
| Score V4 fusion | +0,021 | +1,4 | +0,021 | +1,1 | 46,7 % (46,3 %) | +1,1 % |
| Croissance | −0,015 | −0,7 | −0,012 | −0,4 | – (–) | – |
| Résultats | −0,005 | −0,3 | −0,005 | −0,2 | – (–) | – |
| Momentum | +0,018 | +0,6 | +0,006 | +0,1 | – (–) | – |
| Qualité | +0,008 | +0,5 | +0,007 | +0,3 | – (–) | – |
| Valorisation | +0,003 | +0,2 | +0,004 | +0,2 | – (–) | – |
| Risque | +0,001 | +0,0 | +0,011 | +0,2 | – (–) | – |
| Risque (au sein du secteur) | +0,014 | +0,4 | +0,028 | +0,6 | – (–) | – |
| Momentum résiduel | +0,010 | +0,4 | −0,009 | −0,3 | – (–) | – |
| Momentum résiduel (au sein du secteur) | +0,011 | +0,6 | +0,001 | +0,0 | – (–) | – |
| Résultats (au sein du secteur) | +0,001 | +0,1 | +0,002 | +0,1 | – (–) | – |
| Rachats nets | +0,021 | +1,6 | +0,034 | +1,9 | – (–) | – |
| Valorisation (données contrôlées) | +0,003 | +0,2 | +0,003 | +0,1 | – (–) | – |

## 5. Exposition sectorielle moyenne (poids aux revues)

| Stratégie | Industrials | Consumer Staples | Consumer Discretionary | Health Care | Information Technology | Utilities | Materials | Energy | Communication Services | Inconnu |
|---|---|---|---|---|---|---|---|---|---|---|
| V1 (référence) | 15 % | 17 % | 13 % | 15 % | 9 % | 14 % | 8 % | 4 % | 4 % | – |
| V2 (référence) | 16 % | 14 % | 17 % | 13 % | 15 % | 10 % | 8 % | 5 % | 4 % | – |
| V3 (référence) | 16 % | 17 % | 15 % | 14 % | 10 % | 14 % | 7 % | 4 % | 4 % | – |
| V1+ | 14 % | 10 % | 14 % | 13 % | 14 % | 10 % | 12 % | 10 % | 4 % | – |
| V2+ | 14 % | 13 % | 14 % | 13 % | 13 % | 10 % | 10 % | 7 % | 6 % | 0 % |
| V3+ | 14 % | 14 % | 12 % | 14 % | 12 % | 12 % | 10 % | 7 % | 5 % | – |
| V4 fusion | 14 % | 14 % | 12 % | 13 % | 12 % | 14 % | 8 % | 8 % | 4 % | – |

## 6. Données

- Couverture des nouvelles mesures (part des titres classables) : res_12_1 100 %, net_iss 96 %, risk_sec 100 %, mom_res 100 %, buyback 96 %, value_chk 98 %
- Corrélation de rang moyenne avec les anciens facteurs : mom_res~momentum +0,82, risk_sec~risk +0,80, buyback~quality +0,09, buyback~value +0,37, buyback~momentum −0,04, value_chk~value +1,00, earnings_sec~earnings +0,97, mom_res_sec~mom_res +0,90
- Rachats nets : variation annuelle médiane du nombre d'actions : −0,8 % (quartiles −2,8 % ; +0,4 %)
- Dispersion entre secteurs du score de risque (2026-10-15) : classé sur tout l'univers 17,3 points, au sein du secteur 0,0 points
- Titres au nombre d'actions suspect (au moins une date) : 34 : GRMN (2016-04-29 → 2019-02-15, 36 dates), PARA (2024-05-31 → 2025-07-31, 29 dates), LEN (2011-10-17 → 2012-09-28, 23 dates), VTRS (2020-11-30 → 2021-10-29, 23 dates), CNX (2011-05-16 → 2016-02-29, 20 dates), PKG (2023-05-15 → 2026-04-30, 17 dates), CNP (2011-11-15 → 2012-07-31, 14 dates), LIN (2018-11-15 → 2019-05-31, 14 dates), WAT (2026-05-15 → 2026-11-03, 13 dates), QCOM (2011-04-29 → 2012-01-31, 12 dates), ECHO (2026-06-30 → 2026-11-03, 10 dates), YUM (2016-10-17 → 2017-02-15, 9 dates), EP (2011-08-31 → 2012-05-15, 8 dates), ETN (2012-11-15 → 2013-02-28, 8 dates), FTI (2017-01-17 → 2017-04-28, 8 dates), DXC (2017-04-17 → 2017-07-31, 8 dates), AEP (2011-05-16 → 2012-05-15, 7 dates), WHR (2011-07-29 → 2011-10-31, 7 dates), ETR (2011-05-16 → 2011-07-29, 6 dates), CPWR (2011-09-15 → 2011-12-30, 6 dates), AMD (2012-08-15 → 2012-10-31, 6 dates), ORCL (2012-09-28 → 2012-12-17, 6 dates), CLX (2013-02-15 → 2013-04-30, 6 dates), PRGO (2013-11-15 → 2014-01-31, 6 dates), STX (2015-05-15 → 2015-07-31, 6 dates), NFLX (2015-07-31 → 2015-10-15, 6 dates), AMCR (2019-06-17 → 2019-08-30, 6 dates), GOOGL (2022-07-29 → 2022-10-17, 6 dates), EIX (2020-02-28 → 2020-04-30, 5 dates), CCL (2021-01-29 → 2021-03-31, 5 dates)
- XOM (diagnostic) : 2 états, concepts 12 mois : – ; CA 12 mois du jour : –, actions : 4079222444.0
- WAT (diagnostic) : 71 états, concepts 12 mois : capex, cfo, cost_of_revenue, dna, gross_profit, interest_expense, net_income, operating_income, pretax_income, revenue ; CA 12 mois du jour : 4644249000.0, actions : 98204000000.0
- FERG (diagnostic) : 9 états, concepts 12 mois : capex, cfo, cost_of_revenue, dna, gross_profit, interest_expense, net_income, operating_income, pretax_income, revenue ; CA 12 mois du jour : –, actions : 193452717.0

## Limites

- Période entière déjà vue : ces écarts sont des indices, pas des preuves ; plusieurs leviers testés à la fois rendent probable qu'un d'eux paraisse bon par hasard.
- Sociétés sans cours Yahoo absentes (biais de survivance, voir l'onglet Données).
- Rachats nets : nombre d'actions de la page de garde des rapports (ou moyenne diluée), comparé à celui d'il y a un an de même source ; les erreurs de données passent en partie.

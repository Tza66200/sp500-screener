# Screener S&P 500 — position trading sur 12 à 18 mois

Classement quantitatif des actions du S&P 500, portefeuille modèle de 20 lignes et backtest
honnête, publiés sur un site web actualisé chaque soir par GitHub Actions. Aucun serveur à
maintenir, aucun coût.

Trois modèles coexistent (sélecteur en haut du site) :

| Modèle | Statut | Pondérations |
|---|---|---|
| V1 hybride | figée le 16/10/2026 avant tout test | croissance 25, momentum 25, qualité 20, valorisation 15, risque 15 |
| V2 littérature | enregistrée le 16/10/2026 à 13 h 15, après lecture des résultats de V1 | résultats 20, momentum 35, qualité 25, valorisation 10, risque 10 |
| V3 risque maîtrisé (par défaut) | enregistrée le 17/10/2026 à 8 h 46, après lecture des résultats de V1 et V2 | résultats 20, momentum 25, qualité 25, valorisation 15, risque 15 |

V2 et V3 ont été conçues en connaissant les résultats de 2011-2020 : seule la période réservée
(depuis 2021) et le suivi réel peuvent les valider. Les trois modèles seront jugés ensemble,
une seule fois, à la révélation de cette période, sans retenir le meilleur après coup.

Outil d'aide à la décision : ce n'est ni un conseil en investissement, ni un système d'ordres.

## Fonctionnement

```
GitHub Actions (chaque soir de semaine, 22 h 40 UTC)
  ├─ composition de l'indice   Wikipedia + historique fja05680/sp500
  ├─ cours                     Yahoo Finance via yfinance
  ├─ comptes                   SEC EDGAR (companyfacts, submissions)
  ├─ calculs                   python -m screener.pipeline run
  ├─ historique des classements → commit dans history/
  └─ site statique (site/)     → GitHub Pages
```

Les données téléchargées sont gardées dans le cache d'Actions : seuls les comptes des sociétés
ayant déposé un nouveau rapport sont retéléchargés.

## Mise en place

1. Créer un dépôt GitHub public et y pousser ce dossier.
2. **Settings → Secrets and variables → Actions** : ajouter le secret `SEC_CONTACT_EMAIL`
   (la SEC exige une adresse de contact dans chaque requête ; elle n'est jamais publiée).
3. **Settings → Pages → Source** : choisir **GitHub Actions**.
4. **Actions → Actualisation → Run workflow**. Le premier passage prend 20 à 40 minutes.
5. Le site est à l'adresse `https://<utilisateur>.github.io/<dépôt>/`.

Après chaque calcul, les fichiers de résultats (`site/data`), le journal et un fichier
`diagnostics.json` sont aussi copiés dans la branche `publication`. Ce dernier liste, pour chaque
société incomplète, les mesures manquantes et les étiquettes XBRL candidates : c'est le point de
départ pour compléter `config/xbrl_concepts.yaml`.

GitHub envoie un e-mail si une actualisation échoue. Le site affiche aussi un avertissement
si les données ont plus de quatre jours.

## Réglages

| Fichier | Contenu |
|---|---|
| `config/settings.yaml` | pondérations, filtres, règles du portefeuille, frais |
| `config/protocol.yaml` | protocole de validation figé : variantes, critères, période réservée |
| `config/vetoes.yaml` | vetos qualitatifs (titre écarté avec justification, sans toucher au score) |
| `config/xbrl_concepts.yaml` | correspondance des étiquettes comptables XBRL |

Modifier un fichier depuis l'interface web de GitHub relance automatiquement le calcul.

**Période réservée** : les résultats depuis 2021 sont masqués. Quand le modèle est figé,
passer `holdout.revealed` à `true` dans `config/protocol.yaml`, une seule fois. Ne plus modifier
le modèle en fonction de ce qui apparaît alors.

## En local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export SEC_CONTACT_EMAIL="vous@exemple.com"
python -m screener.pipeline run            # tout
python -m screener.pipeline run --offline  # recalcul depuis le cache data/
python -m http.server -d site 8000         # puis http://localhost:8000
python -m pytest -q
```

## Structure

| Module | Rôle |
|---|---|
| `screener/universe.py` | membres actuels et historiques, correspondance ticker → CIK |
| `screener/prices.py` | cours quotidiens, fractionnements |
| `screener/sec.py` | téléchargement SEC avec limite de débit |
| `screener/fundamentals.py` | fondamentaux datés à leur publication (trimestres, 12 mois glissants) |
| `screener/features.py` | les 11 mesures à une date donnée |
| `screener/scoring.py` | percentiles, facteurs, score, filtres |
| `screener/portfolio.py` | règles d'achat et de vente |
| `screener/backtest.py` | simulation et mesures de performance |
| `screener/ic.py` | analyse facteur par facteur |
| `screener/audit.py` | couverture des données et biais de survivance |
| `screener/report.py` | fichiers JSON du site, exports CSV et Excel |
| `site/` | application web (HTML, CSS, JavaScript sans dépendance) |

## Limites

- Yahoo Finance ne fournit généralement pas les cours des sociétés retirées de la cote :
  le backtest les omet, ce qui l'embellit. L'onglet Données chiffre ce biais.
- yfinance est une bibliothèque non officielle ; en cas de panne, la série précédente est
  conservée et signalée.
- Pas d'estimations d'analystes : la croissance repose sur les chiffres publiés.
- Financières et immobilier exclus en V1.
- Le filtre « offre de rachat » n'est appliqué qu'au classement du jour.
- Certaines sociétés publient leurs comptes avec des étiquettes XBRL propres (Caterpillar,
  Ford, Phillips 66…) : la mesure concernée reste alors vide, jamais estimée. Quand une dette
  existe mais reste introuvable, elle est déclarée inconnue plutôt que nulle.
- La SEC intègre parfois un rapport à ses données XBRL avec plusieurs semaines de retard ;
  la fiche de la société le signale.

Police Archivo sous licence SIL Open Font License (`site/fonts/OFL.txt`).

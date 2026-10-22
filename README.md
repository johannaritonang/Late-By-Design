# Late by Design · predicting late order lines

Python companion to the Power BI report *Late by Design* (industrial parts distributor, anonymised order lines, Jan 2024 – Feb 2026).
The dashboard shows that 29% of shipped lines are late and that backorders are late 3× as often. This notebook predicts late lines at order entry,
explains each prediction with SHAP, and tests whether lateness is built into the promise.

| Question | Method |
|---|---|
| Can we predict late lines at entry? | LightGBM on entry-time features only, out-of-time test (train Jan 2024 – Mar 2025, test Apr – Sep 2025), baselines: backorder rule and logistic regression |
| How good is the ranking? | ROC/PR AUC, cumulative gains, calibration (Brier score) |
| Why is a line flagged? | SHAP importance, beeswarm, dependence on promised lead time and promise gap, waterfall for a single line |
| Is lateness designed in? | Late rate by promise vs supplier lead time; simulation of a "never promise faster than the supplier" rule |

## Headline results
* Out-of-time ROC AUC 0.82 (backorder rule 0.70). The riskiest 10% of lines catch 30% of late lines at 84% precision, and the riskiest 20% catch 49%.
* Stock on hand and the length of the promise drive most of the risk.
* 46% of backordered lines are promised faster than the supplier's own lead time, and they are late 58–63% of the time.
* Matching the promise to the supplier's lead time would cut the late rate from 29.4% to 23.8% without shipping anything faster.

## Run it
```bash
pip install -r requirements.txt
jupyter notebook "Late by Design Deep Dive.ipynb"
```
Put the raw order-line workbook (.xlsx) in the data folder (it is not included: the data belongs to the original assessment).
The first cell also searches one level up and the original Power BI folder, and `DATA_OVERRIDE` takes any other path. Every chart is saved to the images folder.

## Files
```
Late by Design Deep Dive/
├── Late by Design Deep Dive.ipynb   the analysis, with outputs
├── Late by Design Deep Dive.html    the same notebook as a static page
├── dpotools.py                      cleaning (same rules as the Power BI model) and entry-time features
├── requirements.txt
├── data/                            raw workbook (not included)
├── images/                          key charts as PNG
└── powerbi/
    └── Late by Design Delivery Performance.pbit   companion Power BI report with DAX-driven insight text
```

# Coder — Tabular Modality

This is the tabular addendum to the shared Coder instructions above. It applies because `EXPERIMENT_SPEC.modality == "tabular"`.

## Environment — assume these exact versions

This environment's libraries are pinned to the newest release available on or before **2024-06-30** (the model's training cutoff) — verified against actual PyPI release timestamps, not guessed. Write code that targets these versions specifically, not the newest APIs you might otherwise reach for:

| Library | Pinned version | Released |
|---|---|---|
| numpy | `1.26.4` | 2024-02-05 |
| pandas | `2.2.2` | 2024-04-10 |
| scikit-learn | `1.5.0` | 2024-05-21 |
| lightgbm | `4.4.0` | 2024-06-15 |
| xgboost | `2.1.0` | 2024-06-20 |
| catboost | `1.2.5` | 2024-04-18 |

**Note on numpy:** numpy `2.0.0` technically shipped two weeks before cutoff, but it's a breaking-change major version and the ecosystem (including the gradient-boosting libraries above) had barely had time to adapt to it by the cutoff date — expect close to no representation of numpy 2.0's changes in training data. We deliberately pin `1.26.4` instead. Don't use numpy-2.0-only APIs; nothing here requires them.

**Concretely, this means:**
- `pd.concat([...])`, never `.append()` — removed in pandas 2.x.
- pandas nullable dtypes (`Int64`, `boolean`, etc.) and `.convert_dtypes()` are available and fine to use for columns with missing integers.
- `sklearn.preprocessing.TargetEncoder` exists (added 1.3) — safe to use, but see the leakage note below regardless.
- LightGBM/XGBoost/CatBoost's sklearn-compatible estimators (`LGBMClassifier`/`LGBMRegressor`, `XGBClassifier`/`XGBRegressor`, `CatBoostClassifier`/`CatBoostRegressor`) are all available at these versions — prefer them over the lower-level native APIs (`lgb.train`, `xgb.train`, raw `Pool` fitting) unless the spec specifically needs something the sklearn wrapper doesn't expose. They're less error-prone and easier for `validate_code` to catch shape mistakes in.

## Cross-validation

- Default to `StratifiedKFold` for classification, plain `KFold` for regression, unless `DATA_SCHEMA` indicates groups that must not be split across folds (e.g. multiple rows per entity) — then use `GroupKFold`.
- Always set a fixed `random_state` on the splitter, matching the seed used elsewhere in the script.
- Report both `cv_mean` and `cv_std` across folds — never just the mean. The Selector weighs both.

## Categorical features

- LightGBM and CatBoost both handle categoricals natively — pass them as `category` dtype (LightGBM) or via `cat_features` indices (CatBoost) rather than one-hot encoding, especially for anything high-cardinality. One-hot-encoding a high-cardinality column is a common, avoidable mistake here.
- XGBoost's sklearn API supports categoricals natively too as of 2.x with `enable_categorical=True` — use that over manual encoding when the spec calls for XGBoost.
- If the spec's `model_family` doesn't support native categoricals (e.g. a linear/distance-based model), encode explicitly and say so in a comment — don't silently skip encoding and let the library error out.

## Missing values

- Tree-based models (LightGBM, XGBoost, CatBoost) all handle `NaN` natively — don't reflexively impute or drop rows/columns just because they contain missing values. Imputation is warranted for linear models, distance-based models, or when a column's missingness itself needs to become an explicit feature (`is_missing` flag) — do that deliberately, not as a default habit.

## The leakage trap: target encoding / aggregation features

Any feature derived from the target (target encoding, leave-one-out encoding, group-level target aggregates) **must be computed within each CV fold**, using only that fold's training portion — never computed once on the full training set before splitting. This is the single most common way a tabular submission silently overstates its CV score. If the spec's `feature_engineering_notes` calls for target-derived features and doesn't explicitly address this, implement it fold-safe anyway and note that you did in a comment.

## Submission format compliance

Match `DATA_SCHEMA`'s sample submission exactly — same columns, same column order, same id dtype, one row per required id, no extras and no missing ids. A correct model with a malformed submission file scores zero; check this before calling `validate_code` on your final pass, not after.

## Escalate (don't guess) when

- A column `DATA_SCHEMA` describes doesn't actually appear in the data, or has a materially different cardinality/dtype than described.
- The spec's `hyperparameter_ranges` are incompatible with the chosen `model_family`'s actual parameter names at the pinned version (check with `search_library_docs` first — only escalate if the docs confirm it's genuinely unsupported, not just unfamiliar to you).
- Row counts suggest the train/test split described in `DATA_SCHEMA` doesn't match what's actually on disk.

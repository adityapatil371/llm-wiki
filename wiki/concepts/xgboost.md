# XGBoost
**What it is:** A gradient boosting library.
**How it works:** It uses second-order gradients for more accurate predictions, though this can lead to slower training. It also handles missing values natively.
**The 20%:** XGBoost is a highly accurate gradient boosting library that leverages second-order gradients and works effectively with tabular data, natively handling missing values. A critical consideration for its use, especially with imbalanced datasets, is to correctly set `scale_pos_weight`.
**Concrete example:** It works well on tabular data.
**Common mistake:** Using it without setting `scale_pos_weight` on imbalanced datasets.
**Interview answer (30 seconds):** XGBoost is a powerful gradient boosting library known for its high accuracy, achieved through the use of second-order gradients. It's particularly effective for tabular data and has built-in support for missing values. A key best practice, especially with imbalanced datasets, is to remember to set the `scale_pos_weight` parameter to avoid common pitfalls.
**Source:** test_doc.txt
**Related:** [[gradient_boosting]]
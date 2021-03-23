#!/usr/bin/env python
from sklearn.metrics import (
    jaccard_score,
    hamming_loss,
    precision_recall_fscore_support,
    confusion_matrix,
)

# from scipy.sparse import csr_matrix
import numpy as np


def multiclass_metrics(targets, preds, class_names):
    """provide a list or np.array of 0,1 targets and predictions"""
    epoch_metrics = {}

    # Confusion matrix if not multi-label
    if max(np.sum(targets, 1)) <= 1 and max(np.sum(preds, 1)) <= 1:
        # requires class labels not one-hot
        t = np.argmax(targets, 1)
        p = np.argmax(preds, 1)
        epoch_metrics["confusion_matrix"] = confusion_matrix(t, p)

    # Store per-class precision, recall, and f1
    class_pre, class_rec, class_f1, _ = precision_recall_fscore_support(
        targets, preds, average=None, zero_division=0
    )
    for i, class_i in enumerate(class_names):
        epoch_metrics.update(
            {
                class_i: {
                    "precision": class_pre[i],
                    "recall": class_rec[i],
                    "f1": class_f1[i],
                }
            }
        )

    # macro scores are averaged across classes
    epoch_metrics["precision"] = class_pre.mean()
    epoch_metrics["recall"] = class_rec.mean()
    epoch_metrics["f1"] = class_f1.mean()

    epoch_metrics["jaccard"] = jaccard_score(targets, preds, average="macro")
    epoch_metrics["hamming_loss"] = hamming_loss(targets, preds)

    return epoch_metrics


def binary_metrics(targets, preds, class_names=[0, 1]):
    """labels should be single-target"""
    if max(np.sum(targets, 1)) > 1:
        raise ValueError(
            "Labels must be single-target for binary classification."
            " Use multi-target classifier if multiple classes can be present."
        )

    epoch_metrics = {}

    # Confusion matrix requires numeric not one-hot labels
    t = np.argmax(targets, 1)
    p = np.argmax(preds, 1)
    epoch_metrics["confusion_matrix"] = confusion_matrix(t, p)

    # precision, recall, and f1
    pre, rec, f1, _ = precision_recall_fscore_support(
        targets, preds, average=None, zero_division=0
    )
    epoch_metrics.update({"precision": pre[1], "recall": rec[1], "f1": f1[1]})

    epoch_metrics["jaccard"] = jaccard_score(targets, preds, average="macro")
    epoch_metrics["hamming_loss"] = hamming_loss(targets, preds)

    return epoch_metrics

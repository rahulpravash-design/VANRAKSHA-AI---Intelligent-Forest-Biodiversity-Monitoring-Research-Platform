"""Fine-tune the vision backend on a labelled image dataset.

Two modes, matching the two vision tasks the platform has:

``detect``
    Wildlife detection with Ultralytics YOLO.  Expects a standard YOLO dataset
    YAML (``path``, ``train``, ``val``, ``names``).

``classify``
    Species classification with Ultralytics' classification trainer.  Expects
    ``train/<class>/*.jpg`` and ``val/<class>/*.jpg``.

Directory names should be scientific names with underscores
(``Bos_gaurus``) so the resulting class list maps onto the species table without
a manual mapping step.

Usage::

    python -m ai.training.train_vision classify --data datasets/images --out ai/models/weights
    python -m ai.training.train_vision detect --data datasets/wildlife.yaml --out ai/models/weights
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from ai.vision.ultralytics_backend import ultralytics_available

logger = logging.getLogger("ai.training.vision")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("detect", "classify"))
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="output directory")
    parser.add_argument(
        "--base-weights",
        default=None,
        help="starting checkpoint (default: yolo11n.pt / yolo11n-cls.pt)",
    )
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--seed", type=int, default=20260917)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not ultralytics_available():
        logger.error(
            "ultralytics is not installed. Install the optional dependencies first:\n"
            "  pip install -r ai/requirements-trained.txt"
        )
        return 2
    if not args.data.exists():
        logger.error("dataset path does not exist: %s", args.data)
        return 2

    from ultralytics import YOLO

    default_weights = "yolo11n.pt" if args.mode == "detect" else "yolo11n-cls.pt"
    model = YOLO(args.base_weights or default_weights)
    args.out.mkdir(parents=True, exist_ok=True)

    logger.info("training %s for %d epochs on %s", args.mode, args.epochs, args.data)
    model.train(
        data=str(args.data),
        epochs=args.epochs,
        imgsz=args.image_size if args.mode == "detect" else 224,
        batch=args.batch_size,
        device=args.device,
        seed=args.seed,
        project=str(args.out),
        name=f"vanraksha-{args.mode}",
        exist_ok=True,
    )
    metrics = model.val()
    logger.info("validation metrics: %s", getattr(metrics, "results_dict", metrics))
    logger.info(
        "point the platform at the best checkpoint:\n"
        "  AI_VISION_WEIGHTS=%s/vanraksha-%s/weights/best.pt",
        args.out,
        args.mode,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

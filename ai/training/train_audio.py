"""Train the acoustic CNN on a folder of labelled recordings.

Expected layout — one directory per species, named with the scientific name so
the checkpoint's class list maps cleanly onto the platform's species table::

    datasets/audio/
      Myophonus_horsfieldii/
        rec_0001.wav
        ...
      Pavo_cristatus/
        ...

The split is made *by recording*, not by clip, so clips cut from the same
recording never land on both sides of the split — the single most common way an
acoustic classifier reports an accuracy it does not have.

Usage::

    python -m ai.training.train_audio --data datasets/audio --out ai/models/weights/audio.pt
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from pathlib import Path

import numpy as np

from ai.audio.torch_backend import TARGET_FRAMES, build_model, prepare_input, torch_available
from ai.preprocessing.audio import AudioValidationError, decode_audio

logger = logging.getLogger("ai.training.audio")
AUDIO_SUFFIXES = {".wav", ".wave", ".flac", ".ogg", ".mp3"}


def collect(data_root: Path) -> dict[str, list[Path]]:
    classes: dict[str, list[Path]] = {}
    for directory in sorted(p for p in data_root.iterdir() if p.is_dir()):
        files = sorted(
            f for f in directory.rglob("*") if f.suffix.lower() in AUDIO_SUFFIXES
        )
        if files:
            classes[directory.name.replace("_", " ")] = files
    return classes


def split_by_recording(
    files: list[Path], validation_share: float, rng: random.Random
) -> tuple[list[Path], list[Path]]:
    """Split on the recording stem so clips from one recording stay together."""
    groups: dict[str, list[Path]] = {}
    for path in files:
        # `rec_0007_clip3.wav` and `rec_0007_clip4.wav` share a recording.
        stem = path.stem.split("_clip")[0]
        groups.setdefault(stem, []).append(path)
    keys = sorted(groups)
    rng.shuffle(keys)
    cut = max(1, int(len(keys) * (1.0 - validation_share)))
    train = [p for key in keys[:cut] for p in groups[key]]
    validation = [p for key in keys[cut:] for p in groups[key]]
    return train, validation


def load_batch(paths: list[Path], n_mels: int, sample_rate: int) -> np.ndarray:
    patches = []
    for path in paths:
        try:
            audio = decode_audio(path, target_sample_rate=sample_rate)
        except AudioValidationError as exc:
            logger.warning("skipping %s: %s", path.name, exc)
            continue
        patches.append(prepare_input(audio, n_mels=n_mels, target_frames=TARGET_FRAMES))
    if not patches:
        return np.empty((0, 1, n_mels, TARGET_FRAMES), dtype=np.float32)
    return np.stack(patches)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, required=True, help="dataset root")
    parser.add_argument("--out", type=Path, required=True, help="checkpoint path")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--n-mels", type=int, default=64)
    parser.add_argument("--sample-rate", type=int, default=22_050)
    parser.add_argument("--validation-share", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=20260917)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not torch_available():
        logger.error(
            "PyTorch is not installed. Install the optional dependencies first:\n"
            "  pip install -r ai/requirements-trained.txt"
        )
        return 2
    if not args.data.is_dir():
        logger.error("dataset root does not exist: %s", args.data)
        return 2

    import torch
    from torch import nn, optim

    classes = collect(args.data)
    if len(classes) < 2:
        logger.error("need at least two class directories under %s", args.data)
        return 2
    labels = sorted(classes)
    logger.info("%d classes, %d files", len(labels), sum(len(v) for v in classes.values()))

    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)
    train_items: list[tuple[Path, int]] = []
    validation_items: list[tuple[Path, int]] = []
    for index, label in enumerate(labels):
        train, validation = split_by_recording(classes[label], args.validation_share, rng)
        train_items += [(p, index) for p in train]
        validation_items += [(p, index) for p in validation]
    logger.info("train=%d validation=%d", len(train_items), len(validation_items))

    device = torch.device(args.device)
    model = build_model(len(labels), n_mels=args.n_mels).to(device)
    optimiser = optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=1e-4)
    criterion = nn.CrossEntropyLoss()
    best_accuracy = 0.0

    for epoch in range(1, args.epochs + 1):
        model.train()
        rng.shuffle(train_items)
        total_loss = 0.0
        batches = 0
        for start in range(0, len(train_items), args.batch_size):
            batch = train_items[start : start + args.batch_size]
            features = load_batch([p for p, _ in batch], args.n_mels, args.sample_rate)
            if features.shape[0] == 0:
                continue
            targets = torch.tensor([label for _, label in batch][: features.shape[0]])
            inputs = torch.from_numpy(features).to(device)
            optimiser.zero_grad()
            loss = criterion(model(inputs), targets.to(device))
            loss.backward()
            optimiser.step()
            total_loss += float(loss.item())
            batches += 1

        model.eval()
        correct = seen = 0
        with torch.no_grad():
            for start in range(0, len(validation_items), args.batch_size):
                batch = validation_items[start : start + args.batch_size]
                features = load_batch([p for p, _ in batch], args.n_mels, args.sample_rate)
                if features.shape[0] == 0:
                    continue
                targets = torch.tensor([label for _, label in batch][: features.shape[0]])
                predicted = model(torch.from_numpy(features).to(device)).argmax(dim=1).cpu()
                correct += int((predicted == targets).sum())
                seen += int(targets.numel())
        accuracy = correct / seen if seen else 0.0
        logger.info(
            "epoch %d/%d loss=%.4f val_accuracy=%.4f",
            epoch,
            args.epochs,
            total_loss / max(batches, 1),
            accuracy,
        )
        if accuracy >= best_accuracy:
            best_accuracy = accuracy
            args.out.parent.mkdir(parents=True, exist_ok=True)
            torch.save(
                {
                    "state_dict": model.state_dict(),
                    "classes": labels,
                    "n_mels": args.n_mels,
                    "sample_rate": args.sample_rate,
                    "version": f"e{epoch}-acc{accuracy:.3f}",
                    "seed": args.seed,
                },
                args.out,
            )
            logger.info("checkpoint written to %s", args.out)

    (args.out.parent / f"{args.out.stem}-metadata.json").write_text(
        json.dumps(
            {
                "classes": labels,
                "best_validation_accuracy": best_accuracy,
                "epochs": args.epochs,
                "seed": args.seed,
                "split": "grouped by recording stem",
            },
            indent=2,
        )
    )
    logger.info("done; best validation accuracy %.4f", best_accuracy)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

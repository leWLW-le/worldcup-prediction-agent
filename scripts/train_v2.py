"""Train only from explicit 90-minute historical records with provenance."""

import argparse

from app.pipelines.training import load_history, train_bundle

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("history_json")
    parser.add_argument("output_dir")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--walk-forward-folds", type=int, default=0)
    args = parser.parse_args()
    history, provenance = load_history(args.history_json)
    if args.walk_forward_folds:
        from app.pipelines.backtest import walk_forward

        print(
            walk_forward(
                history,
                args.output_dir,
                provenance,
                folds=args.walk_forward_folds,
                epochs=args.epochs,
            )
        )
    else:
        print(train_bundle(history, args.output_dir, provenance, epochs=args.epochs))

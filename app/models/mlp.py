"""Plain feed-forward model; input shape is a hard contract."""

from torch import nn

from app.features.prematch import COLUMNS


class MatchMLP(nn.Module):
    def __init__(self, input_dim=len(COLUMNS) + 1):
        super().__init__()
        self.input_dim = input_dim
        self.layers = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.Dropout(0.15),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, 3),
        )

    def forward(self, x):
        if x.ndim != 2 or x.shape[1] != self.input_dim:
            raise ValueError(f"Expected (batch, {self.input_dim}); got {tuple(x.shape)}")
        return self.layers(x)

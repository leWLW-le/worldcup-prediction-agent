#!/usr/bin/env bash
set -euo pipefail
# V2 creates additive tables during application startup. Never rewrite stored forecasts.
python -c "from app.core.config import get_settings, validate_settings; validate_settings(get_settings())"

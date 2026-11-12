import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_tmp = Path(tempfile.mkdtemp(prefix="mt-test-"))
shutil.copytree(ROOT / "marketing_team" / "knowledge", _tmp / "knowledge")
os.environ.update(MT_DATA_DIR=str(_tmp / "data"), MT_KNOWLEDGE_DIR=str(_tmp / "knowledge"),
                  MT_LLM_PROVIDER="offline", MT_API_KEY="")
for k in ("WHATSAPP_TOKEN", "SLACK_WEBHOOK_URL", "TELEGRAM_BOT_TOKEN", "STRIPE_API_KEY", "STRIPE_WEBHOOK_SECRET"):
    os.environ.pop(k, None)
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def fresh_data():
    from marketing_team import seed
    seed.seed(reset=True)
    yield

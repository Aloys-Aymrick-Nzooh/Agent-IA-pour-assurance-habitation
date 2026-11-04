"""Configuration partagée de l'agent (lue depuis .env)."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

STORAGE_PATH = Path(os.getenv("STORAGE_PATH", "./storage")).resolve()
CONVERSATIONS_PATH = STORAGE_PATH / "conversations"

DOCUMENT_TYPE_DIRS = {
    "CG": "cg",
    "CP": "cp",
    "AVENANT": "avenant",
    "ANNEXE": "annexe",
}

TOP_K = 6


# Traçage d'un tour d'agent (fichier traces.jsonl dans le dossier de la conversation).
# off (défaut) | summary (textes tronqués) | full (prompts et pages complets).
# Les traces contiennent des extraits de contrats
AGENT_TRACE_MODE = os.getenv("AGENT_TRACE", "off").strip().lower()
AGENT_TRACE_ENABLED = AGENT_TRACE_MODE in ("summary", "full", "1", "true", "on")
AGENT_TRACE_FULL = AGENT_TRACE_MODE == "full"
 
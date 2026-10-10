#!/usr/bin/env python3
"""
Alertes marché 🟢🔴 : États-Unis, Londres, Tokyo
Envoie une notification ntfy après chaque annonce économique importante.
Lancé par GitHub (.github/workflows/alertes.yml) toutes les 10 minutes aux heures d'annonce.
"""
import datetime as dt
import json
import os
import sys
import time
from zoneinfo import ZoneInfo

import requests

# ---------- Réglages ----------
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
MODELE = "claude-sonnet-5-5"
PARIS = ZoneInfo("Europe/Paris")

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_SEMAINE = os.path.join(DOSSIER, "semaine.json")
FICHIER_ETAT = os.path.join(DOSSIER, "etat.json")

PREMIER_CHECK_MIN = 3
RELANCE_MIN = 4
ABANDON_MIN = 90

PASTILLE = {"favorable": "🟢", "defavorable": "🔴", "neutre": "⚪"}
TAG_NTFY = {"favorable": "green_circle", "defavorable": "red_circle", "neutre": "white_circle"}


def maintenant():
    return dt.datetime.now(PARIS)


def lire_json(chemin, defaut):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defaut


def ecrire_json(chemin, donnees):
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(donnees, f, ensure_ascii=False, indent=2)


def extraire_json(texte):
    texte = texte.replace("```json", "").replace("```", "")
    debuts = [i for i in (texte.find("{"), texte.find("[")) if i != -1]
    if not debuts:
        raise ValueError("Pas de JSON dans la réponse : " + texte[:200])
    fin = max(texte.rfind("}"), texte.rfind("]"))
    return json.loads(texte[min(debuts):fin + 1])


def demander_a_claude(question, recherches_max=5):
    messages = [{"role": "user", "content": question}]
    for _ in range(4):
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": MODELE,
                "max_tokens": 4000,
                "tools": [{"type": "web_search_20250305", "name": "web_search",
                           "max_uses": recherches_max}],
                "messages": messages,
            },
            timeout=240,

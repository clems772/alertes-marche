# Alertes marche : US, Londres, Tokyo -> notification ntfy verte / rouge
import datetime as dt
import json
import os
import sys
import time
from zoneinfo import ZoneInfo

import requests

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
MODELE = "claude-sonnet-5-5"
PARIS = ZoneInfo("Europe/Paris")
DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_SEMAINE = os.path.join(DOSSIER, "semaine.json")
FICHIER_ETAT = os.path.join(DOSSIER, "etat.json")
PASTILLE = {"favorable": "🟢", "defavorable": "🔴", "neutre": "⚪"}
TAG = {"favorable": "green_circle", "defavorable": "red_circle", "neutre": "white_circle"}
DRAPEAU = {"US": "🇺🇸", "UK": "🇬🇧", "JP": "🇯🇵"}
JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
IMPACT = {"fort": "🔥 Fort impact", "moyen_fort": "⚡ Impact moyen à fort",
          "moyen": "〰️ Impact moyen", "faible": "💤 Impact faible"}


def maintenant():
    return dt.datetime.now(PARIS)


def lire(chemin, defaut):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defaut


def ecrire(chemin, donnees):
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(donnees, f, ensure_ascii=False, indent=2)


def extraire_json(texte):
    debut = min([i for i in (texte.find("{"), texte.find("[")) if i != -1] or [-1])
    fin = max(texte.rfind("}"), texte.rfind("]"))
    if debut == -1 or fin == -1:
        raise ValueError("Pas de JSON : " + texte[:200])
    return json.loads(texte[debut:fin + 1])


def demander_a_claude(question, recherches=5):
    messages = [{"role": "user", "content": question}]
    entetes = {"x-api-key": API_KEY, "anthropic-version": "2023-06-01",
               "content-type": "application/json"}
    outils = [{"type": "web_search_20250305", "name": "web_search", "max_uses": recherches}]
    for _ in range(4):
        corps = {"model": MODELE, "max_tokens": 4000, "tools": outils, "messages": messages}
        r = requests.post("https://api.anthropic.com/v1/messages",
                          headers=entetes, json=corps, timeout=240)
        if r.status_code != 200:
            raise RuntimeError("Erreur API " + str(r.status_code) + " : " + r.text[:300])
        rep = r.json()
        if rep.get("stop_reason") == "pause_turn":
            messages.append({"role": "assistant", "content": rep["content"]})
            continue
        morceaux = [b.get("text", "") for b in rep.get("content", []) if b.get("type") == "text"]
        return extraire_json("".join(morceaux))
    raise RuntimeError("Recherche inachevee")


def notifier(titre, message, verdict=None):
    print(titre, "|", message)
    if NTFY_TOPIC:
        requests.post("https://ntfy.sh/", timeout=30, json={
            "topic": NTFY_TOPIC, "title": titre, "message": message,
            "tags": [TAG[verdict]] if verdict in TAG else [], "priority": 4})


def lundi_cible():
    auj = maintenant().date()
    lundi = auj - dt.timedelta(days=auj.weekday())
    if auj.weekday() >= 5:
        lundi = lundi + dt.timedelta(days=7)
    return lundi


def charger_semaine(forcer=False):
    lundi = lundi_cible()
    cache = lire(FICHIER_SEMAINE, {})
    if not forcer and cache.get("lundi") == lundi.isoformat() and cache.get("annonces"):
        return cache["annonces"]
    vendredi = lundi + dt.timedelta(days=4)
    question = (
        "Nous sommes le " + maintenant().strftime("%d/%m/%Y") + ". "
        "Cherche le calendrier economique de la semaine du " + lundi.strftime("%d/%m/%Y")
        + " au " + vendredi.strftime("%d/%m/%Y") + ". "
        "Garde UNIQUEMENT les annonces a fort impact pour les Etats-Unis, le Royaume-Uni et le Japon "
        "(inflation, emploi, PIB, ventes au detail, banques centrales, PMI majeurs). Maximum 15. Une seule ligne par publication : regroupe les variantes d'un meme chiffre (mensuel, annuel, sous-jacent). Inclus OBLIGATOIREMENT les annonces importantes du Royaume-Uni et du Japon de la semaine (PIB, inflation, emploi, BoE, BoJ, prix a la production) meme si elles sont moins suivies que les americaines. "
        "Heures converties en heure de Paris. Reponds UNIQUEMENT par un tableau JSON : "
        '[{"id":"court_unique","pays":"US|UK|JP","nom":"nom tres court en francais, 3 mots maximum, ex: Inflation CPI",'
        '"heure_paris":"AAAA-MM-JJTHH:MM","prevision":"chiffre principal seulement, tres court, ex: 0,6 % sur un mois, ou vide",'
        '"regle":"quand le chiffre est favorable pour les actions",'
        '"impact":"fort|moyen_fort|moyen|faible"}]. '
        "Pour impact, juge l'effet probable sur les marches (actions US et bitcoin) : "
        "fort = CPI US, emploi US, decision ou discours du president de la Fed ; "
        "moyen_fort = PPI US, ventes au detail US ; moyen = chomage hebdo US, PIB ou BoE au Royaume-Uni ; "
        "faible = indicateurs japonais secondaires."
    )
    annonces = demander_a_claude(question, recherches=8)
    annonces.sort(key=lambda a: a["heure_paris"])
    ecrire(FICHIER_SEMAINE, {"lundi": lundi.isoformat(), "annonces": annonces})
    # une notification par annonce, envoyees de la derniere a la premiere
    # pour qu'elles s'affichent dans l'ordre chronologique sur le telephone
    for a in reversed(annonces):
        h = dt.datetime.fromisoformat(a["heure_paris"])
        titre = DRAPEAU.get(a["pays"], "") + " " + a["nom"]
        message = JOURS[h.weekday()] + " " + h.strftime("%d/%m") + " à " + h.strftime("%Hh%M")
        if a.get("prevision"):
            message = message + "\nPrévu : " + a["prevision"]
        if a.get("impact") in IMPACT:
            message = message + "\n" + IMPACT[a["impact"]]
        notifier(titre, message)
        time.sleep(1)
    notifier("Semaine du " + lundi.strftime("%d/%m") + " : " + str(len(annonces)) + " annonces",
             "Le détail est juste en dessous.")
    return annonces


def verifier(a):
    question = (
        "Annonce economique : " + a["nom"] + " (" + a.get("pays", "") + "), prevue le "
        + maintenant().strftime("%d/%m/%Y") + " vers " + a.get("heure", "") + " heure de Paris. "
        "Prevision du consensus : " + (a.get("prevision") or "inconnue, cherche-la") + ". "
        "Cherche le chiffre REELLEMENT publie aujourd'hui (pas celui du mois precedent). "
        'S\'il n\'est pas encore publie, reponds exactement {"publie": false}. '
        "Sinon reponds UNIQUEMENT en JSON : "
        '{"publie": true, "reel": "...", "prevision": "...", '
        '"verdict": "favorable|defavorable|neutre", "explication": "une phrase simple en francais"}. '
        "Le verdict juge l'effet probable sur les actions du pays : favorable = hausse, "
        "defavorable = baisse, neutre = conforme aux attentes. Regle : "
        + a.get("regle", "inflation plus haute = defavorable, croissance plus forte = favorable")
    )
    rep = demander_a_claude(question)
    if rep.get("publie"):
        return rep
    return None


def alerter(a, rep):
    v = rep.get("verdict", "neutre")
    titre = (PASTILLE.get(v, "⚪") + " " + DRAPEAU.get(a.get("pays", ""), "") + " " + a["nom"] + " : " + str(rep.get("reel", "?"))
             + " (prevu " + str(rep.get("prevision", "?")) + ")")
    notifier(titre, rep.get("explication", ""), v)


def une_fois():
    etat = lire(FICHIER_ETAT, {})
    envoyes = set(etat.get("envoyes", []))
    essais = etat.get("essais", {})
    try:
        for a in charger_semaine():
            cle = a["id"] + "@" + a["heure_paris"]
            if cle in envoyes:
                continue
            heure = dt.datetime.fromisoformat(a["heure_paris"]).replace(tzinfo=PARIS)
            ecoule = (maintenant() - heure).total_seconds() / 60
            if ecoule < 3:
                continue
            if ecoule > 90:
                if cle in essais:
                    notifier("⚠️ " + a["nom"], "Chiffre introuvable, demande-le a Claude.")
                envoyes.add(cle)
                continue
            if time.time() - essais.get(cle, 0) < 240:
                continue
            essais[cle] = time.time()
            try:
                a2 = dict(a)
                a2["heure"] = heure.strftime("%H:%M")
                rep = verifier(a2)
            except Exception as e:
                print("Erreur sur", a["nom"], ":", e)
                continue
            if rep:
                alerter(a, rep)
                envoyes.add(cle)
            else:
                print(a["nom"], ": pas encore publie")
    finally:
        limite = time.time() - 14 * 86400
        etat["essais"] = {k: v for k, v in essais.items() if v > limite}
        etat["envoyes"] = sorted(envoyes)[-200:]
        ecrire(FICHIER_ETAT, etat)


if __name__ == "__main__":
    if not API_KEY:
        sys.exit("Il manque le secret ANTHROPIC_API_KEY")
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "--test":
        notifier("🟢 Test reussi", "Les alertes marche arriveront ici.", "favorable")
    elif mode == "--semaine":
        for a in charger_semaine(forcer=True):
            print(a["heure_paris"], a["pays"], a["nom"], a.get("prevision"))
    else:
        une_fois()

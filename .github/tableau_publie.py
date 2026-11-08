"""Tableau public (users/ludvdber/projects/1) : à la publication d'une release du launcher, chaque carte « Prêt »
de la version « Prochaine mise à jour » passe en « Publié », avec la version dans sa prochaine étape.

Lancé par `.github/workflows/tableau.yml`. Bibliothèque standard seule. Le jeton (`PROJET_TOKEN` : jeton
CLASSIQUE, portées `project` et `repo` ; un jeton à grain fin ne peut pas écrire dans le tableau d'un compte
personnel, doc GitHub « Automating Projects using Actions ») est un secret du dépôt ; sans lui, rien ne se fait
et le run le dit sans échouer : le tableau se range alors à la main, comme avant.

    PROJET_TOKEN=... VERSION=1.3.4 python .github/tableau_publie.py [--essai]
"""
import json
import os
import sys
import urllib.request

PROPRIETAIRE = "ludvdber"
NUMERO = 1
PRET, PUBLIE = "Prêt", "Publié"
PROCHAINE = "Prochaine mise à jour · Next update"
ETAPE = "Prochaine étape · Next step"


def gql(jeton: str, requete: str, **variables: object) -> dict:
    corps = json.dumps({"query": requete, "variables": variables}).encode("utf-8")
    req = urllib.request.Request("https://api.github.com/graphql", data=corps, headers={
        "Authorization": f"Bearer {jeton}", "Content-Type": "application/json", "User-Agent": "accio-tableau"})
    # L'adresse est la constante https de GitHub ci-dessus : ni `file:` ni schéma venu de l'extérieur.
    with urllib.request.urlopen(req, timeout=30) as r:  # nosec B310  # noqa: S310
        sortie = json.load(r)
    if "errors" in sortie:
        raise RuntimeError(json.dumps(sortie["errors"], ensure_ascii=False))
    return sortie["data"]


def cartes_a_publier(items: list[dict]) -> list[dict]:
    """Les cartes « Prêt » de la prochaine mise à jour (pur : testé sans réseau)."""
    choisies = []
    for i in items:
        valeurs = {v["field"]["name"]: v.get("name") for v in i["fieldValues"]["nodes"] if v and v.get("field")}
        if valeurs.get("Status") == PRET and valeurs.get("Version") == PROCHAINE:
            choisies.append(i)
    return choisies


def toutes_les_cartes(jeton: str, projet: str) -> list[dict]:
    """Toutes les cartes, page par page (100 au plus par requête)."""
    cartes: list[dict] = []
    apres = None
    while True:
        d = gql(jeton, """query($p: ID!, $a: String) { node(id: $p) { ... on ProjectV2 {
          items(first: 100, after: $a) { pageInfo { hasNextPage endCursor } nodes { id
            content { ... on DraftIssue { title } ... on Issue { title } }
            fieldValues(first: 20) { nodes { ... on ProjectV2ItemFieldSingleSelectValue { name
              field { ... on ProjectV2FieldCommon { name } } } } } } } } } }""", p=projet, a=apres)
        page = d["node"]["items"]
        cartes += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return cartes
        apres = page["pageInfo"]["endCursor"]


def main() -> int:
    jeton = os.environ.get("PROJET_TOKEN", "")
    version = os.environ.get("VERSION", "").lstrip("v")
    essai = "--essai" in sys.argv
    if not jeton:
        print("PROJET_TOKEN absent : tableau laissé tel quel (à ranger à la main).")
        return 0
    if not version:
        print("VERSION absente.")
        return 1
    d = gql(jeton, """query($o: String!, $n: Int!) { user(login: $o) { projectV2(number: $n) { id
      fields(first: 50) { nodes { ... on ProjectV2FieldCommon { id name }
        ... on ProjectV2SingleSelectField { id name options { id name } } } } } } }""", o=PROPRIETAIRE, n=NUMERO)
    projet = d["user"]["projectV2"]
    champs = {f["name"]: f for f in projet["fields"]["nodes"] if f}
    # Tout ce qu'il faut écrire est résolu AVANT la première écriture : une carte passée en « Publié »
    # sans son étape ne serait jamais reprise par un nouveau run (elle n'est plus « Prêt »).
    statut, champ_etape = champs.get("Status"), champs.get(ETAPE)
    publie = next((o["id"] for o in (statut or {}).get("options", []) if o["name"] == PUBLIE), None)
    if statut is None or champ_etape is None or publie is None:
        print(f"Champ « Status », option « {PUBLIE} » ou champ « {ETAPE} » introuvable : rien changé.")
        return 1
    etape = f"Disponible dans le launcher {version} · Available in launcher {version}"
    choisies = cartes_a_publier(toutes_les_cartes(jeton, projet["id"]))
    for i in choisies:
        titre = (i["content"] or {}).get("title", "?")
        print(("[essai] " if essai else "") + f"{titre} -> {PUBLIE}")
        if essai:
            continue
        gql(jeton, """mutation($p: ID!, $i: ID!, $f: ID!, $o: String!) { updateProjectV2ItemFieldValue(input:
          {projectId: $p, itemId: $i, fieldId: $f, value: {singleSelectOptionId: $o}}) { clientMutationId } }""",
            p=projet["id"], i=i["id"], f=statut["id"], o=publie)
        gql(jeton, """mutation($p: ID!, $i: ID!, $f: ID!, $t: String!) { updateProjectV2ItemFieldValue(input:
          {projectId: $p, itemId: $i, fieldId: $f, value: {text: $t}}) { clientMutationId } }""",
            p=projet["id"], i=i["id"], f=champ_etape["id"], t=etape)
    print(f"{len(choisies)} carte(s) passée(s) en {PUBLIE}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

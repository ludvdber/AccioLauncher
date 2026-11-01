"""Le nom lisible d'un mouvement des modèles 3D (Personnages, Bestiaire).

Les fichiers des jeux nomment leurs mouvements en anglais de développeur :
« breath », « TalkLeft2 », « WandCastFlipendoPerfect », « Look_UpL45 ». La liste
sous le modèle les montrait tels quels (revue des écrans, 2026-11-01). 1 001 noms
distincts dans HP1-HP3 : on les traduit MOT À MOT (glossaire), les sorts et les
noms propres restent tels quels, un mot inconnu aussi. L'anglais garde le nom du
jeu, mis en forme. Les mouvements du VISAGE (bouche, paupières, sourcils,
phonèmes de HP2) ne bougent rien de visible sur le corps : `libelle` rend None.
"""

import re

# Mot du jeu → (français, espagnol). Verbes à l'infinitif, comme un menu d'actions.
_GLOSSAIRE: dict[str, tuple[str, str]] = {
    "idle": ("repos", "reposo"),
    "breath": ("respirer", "respirar"),
    "breathe": ("respirer", "respirar"),
    "rest": ("repos", "reposo"),
    "stand": ("debout", "de pie"),
    "walk": ("marcher", "caminar"),
    "run": ("courir", "correr"),
    "trot": ("trotter", "trotar"),
    "jump": ("sauter", "saltar"),
    "land": ("atterrir", "aterrizar"),
    "fall": ("tomber", "caer"),
    "fly": ("voler", "volar"),
    "hover": ("planer", "planear"),
    "glide": ("glisser", "deslizarse"),
    "slide": ("glisser", "deslizarse"),
    "climb": ("grimper", "trepar"),
    "crawl": ("ramper", "gatear"),
    "crouch": ("accroupi", "agachado"),
    "sneak": ("se faufiler", "sigilo"),
    "strafe": ("pas de côté", "paso lateral"),
    "step": ("pas", "paso"),
    "shuffle": ("piétiner", "arrastrar los pies"),
    "turn": ("tourner", "girar"),
    "turning": ("tourner", "girar"),
    "spin": ("pivoter", "girar"),
    "look": ("regarder", "mirar"),
    "lookaround": ("regarder autour", "mirar alrededor"),
    "peek": ("jeter un œil", "asomarse"),
    "peak": ("jeter un œil", "asomarse"),
    "search": ("fouiller", "registrar"),
    "talk": ("parler", "hablar"),
    "conversation": ("conversation", "conversación"),
    "listen": ("écouter", "escuchar"),
    "agree": ("approuver", "asentir"),
    "disagree": ("désapprouver", "discrepar"),
    "dunno": ("je ne sais pas", "no sé"),
    "explain": ("expliquer", "explicar"),
    "nod": ("hocher la tête", "asentir"),
    "shrug": ("hausser les épaules", "encogerse de hombros"),
    "wave": ("saluer", "saludar"),
    "bow": ("s'incliner", "reverencia"),
    "clap": ("applaudir", "aplaudir"),
    "laugh": ("rire", "reír"),
    "snicker": ("ricaner", "reírse"),
    "taunt": ("narguer", "provocar"),
    "point": ("montrer", "señalar"),
    "gesture": ("geste", "gesto"),
    "fidget": ("s'agiter", "inquieto"),
    "stretch": ("s'étirer", "estirarse"),
    "yawn": ("bâiller", "bostezar"),
    "scratch": ("se gratter", "rascarse"),
    "shake": ("secouer", "sacudir"),
    "shiver": ("frissonner", "tiritar"),
    "pant": ("haleter", "jadear"),
    "cough": ("tousser", "toser"),
    "sit": ("assis", "sentado"),
    "sitting": ("assis", "sentado"),
    "situp": ("se redresser", "incorporarse"),
    "lying": ("allongé", "tumbado"),
    "lean": ("s'appuyer", "apoyarse"),
    "sleep": ("dormir", "dormir"),
    "sleeping": ("dormir", "dormir"),
    "sleepy": ("endormi", "somnoliento"),
    "wake": ("se réveiller", "despertar"),
    "groggy": ("groggy", "aturdido"),
    "dizzy": ("étourdi", "mareado"),
    "dazed": ("sonné", "aturdido"),
    "stun": ("assommé", "aturdido"),
    "stunned": ("assommé", "aturdido"),
    "petrified": ("pétrifié", "petrificado"),
    "faint": ("s'évanouir", "desmayarse"),
    "collapse": ("s'effondrer", "desplomarse"),
    "collapsed": ("effondré", "desplomado"),
    "stumble": ("trébucher", "tropezar"),
    "flinch": ("tressaillir", "estremecerse"),
    "recover": ("se relever", "recuperarse"),
    "getup": ("se relever", "levantarse"),
    "standup": ("se lever", "levantarse"),
    "die": ("mourir", "morir"),
    "attack": ("attaquer", "atacar"),
    "hit": ("touché", "golpe"),
    "react": ("réagir", "reaccionar"),
    "knockback": ("projeté", "empujado"),
    "knockdown": ("renversé", "derribado"),
    "charge": ("charger", "embestir"),
    "lunge": ("se fendre", "embestida"),
    "claw": ("griffer", "arañar"),
    "kick": ("donner un coup de pied", "patear"),
    "smash": ("frapper", "golpear"),
    "swing": ("frapper", "golpear"),
    "roar": ("rugir", "rugir"),
    "spit": ("cracher", "escupir"),
    "bite": ("mordre", "morder"),
    "flee": ("fuir", "huir"),
    "rearup": ("se cabrer", "encabritarse"),
    "rear": ("se cabrer", "encabritarse"),
    "rears": ("se cabrer", "encabritarse"),
    "battle": ("combat", "combate"),
    "combat": ("combat", "combate"),
    "duel": ("duel", "duelo"),
    "winner": ("vainqueur", "ganador"),
    "loser": ("vaincu", "perdedor"),
    "cast": ("lancer un sort", "lanzar un hechizo"),
    "castaim": ("viser", "apuntar"),
    "aim": ("viser", "apuntar"),
    "spell": ("sort", "hechizo"),
    "miscast": ("raté", "fallido"),
    "undercast": ("trop faible", "demasiado débil"),
    "perfect": ("parfait", "perfecto"),
    "fast": ("rapide", "rápido"),
    "backfire": ("retour de sort", "rebote"),
    "maintain": ("maintenir", "mantener"),
    "conjure": ("conjurer", "conjurar"),
    "summon": ("invoquer", "invocar"),
    "wand": ("baguette", "varita"),
    "flick": ("coup de baguette", "floritura"),
    "swish": ("moulinet", "floritura"),
    "tap": ("tapoter", "golpear"),
    "sword": ("épée", "espada"),
    "throw": ("lancer", "lanzar"),
    "thrown": ("lancé", "lanzado"),
    "catch": ("attraper", "atrapar"),
    "grab": ("saisir", "agarrar"),
    "take": ("prendre", "tomar"),
    "give": ("donner", "dar"),
    "pickup": ("ramasser", "recoger"),
    "pick": ("ramasser", "recoger"),
    "drop": ("lâcher", "soltar"),
    "hold": ("tenir", "sostener"),
    "carry": ("porter", "llevar"),
    "push": ("pousser", "empujar"),
    "pull": ("tirer", "tirar"),
    "open": ("ouvrir", "abrir"),
    "close": ("fermer", "cerrar"),
    "reach": ("tendre la main", "alcanzar"),
    "drink": ("boire", "beber"),
    "mix": ("mélanger", "mezclar"),
    "stirring": ("touiller", "remover"),
    "wash": ("laver", "lavar"),
    "scrub": ("frotter", "frotar"),
    "tidy": ("ranger", "ordenar"),
    "wipe": ("essuyer", "secar"),
    "buy": ("acheter", "comprar"),
    "mount": ("monter", "montar"),
    "dismount": ("descendre", "desmontar"),
    "takeoff": ("décoller", "despegar"),
    "hang": ("se suspendre", "colgarse"),
    "dangle": ("pendre", "colgar"),
    "vault": ("franchir", "saltar"),
    "leap": ("bondir", "brincar"),
    "bounce": ("rebondir", "rebotar"),
    "dodge": ("esquiver", "esquivar"),
    "avoid": ("esquiver", "esquivar"),
    "stop": ("s'arrêter", "detenerse"),
    "start": ("début", "inicio"),
    "end": ("fin", "fin"),
    "loop": ("boucle", "bucle"),
    "intro": ("arrivée", "entrada"),
    "exit": ("sortie", "salida"),
    "return": ("revenir", "volver"),
    "approach": ("approcher", "acercarse"),
    "alert": ("en alerte", "alerta"),
    "scared": ("effrayé", "asustado"),
    "frantic": ("affolé", "frenético"),
    "angry": ("en colère", "enfadado"),
    "joy": ("joie", "alegría"),
    "positive": ("oui", "sí"),
    "negative": ("non", "no"),
    "pos": ("oui", "sí"),
    "neg": ("non", "no"),
    "success": ("réussi", "logrado"),
    "abort": ("abandonner", "abandonar"),
    "celebrate": ("célébrer", "celebrar"),
    "remember": ("se souvenir", "recordar"),
    "flustered": ("troublé", "nervioso"),
    "ponder": ("réfléchir", "pensar"),
    "disgusted": ("dégoûté", "asqueado"),
    "comehere": ("viens ici", "ven aquí"),
    "head": ("tête", "cabeza"),
    "hands": ("mains", "manos"),
    "bothhands": ("deux mains", "ambas manos"),
    "rhand": ("main droite", "mano derecha"),
    "lhand": ("main gauche", "mano izquierda"),
    "righthand": ("main droite", "mano derecha"),
    "lefthand": ("main gauche", "mano izquierda"),
    "arms": ("bras", "brazos"),
    "crossarms": ("bras croisés", "brazos cruzados"),
    "left": ("à gauche", "a la izquierda"),
    "right": ("à droite", "a la derecha"),
    "l": ("à gauche", "a la izquierda"),
    "r": ("à droite", "a la derecha"),
    "up": ("en haut", "arriba"),
    "down": ("en bas", "abajo"),
    "forward": ("en avant", "adelante"),
    "back": ("en arrière", "atrás"),
    "around": ("autour", "alrededor"),
    "high": ("en hauteur", "alto"),
    "low": ("bas", "bajo"),
    "mid": ("à mi-hauteur", "a media altura"),
    "tall": ("haut", "alto"),
    "hard": ("fort", "fuerte"),
    "wall": ("mur", "pared"),
    "ledge": ("rebord", "cornisa"),
    "ladder": ("échelle", "escalera"),
    "chest": ("coffre", "cofre"),
    "desk": ("bureau", "escritorio"),
    "cabinet": ("armoire", "armario"),
    "book": ("livre", "libro"),
    "spellbook": ("livre de sorts", "libro de hechizos"),
    "potion": ("potion", "poción"),
    "cauldron": ("chaudron", "caldero"),
    "window": ("fenêtre", "ventana"),
    "broom": ("balai", "escoba"),
    "prop": ("objet", "objeto"),
    "item": ("objet", "objeto"),
    "rat": ("rat", "rata"),
    "bed": ("lit", "cama"),
    "portrait": ("portrait", "retrato"),
    "password": ("mot de passe", "contraseña"),
    "panel": ("panneau", "panel"),
    "trap": ("piège", "trampa"),
    "player": ("joueur", "jugador"),
    "cutscene": ("cinématique", "cinemática"),
    "wizard": ("sorcier", "mago"),
    "card": ("carte", "cromo"),
    "acquire": ("obtenir", "obtener"),
    "vendor": ("marchand", "vendedor"),
    "web": ("toile", "telaraña"),
    "stuck": ("coincé", "atrapado"),
    "eat": ("manger", "comer"),
    "and": ("et", "y"),
    "to": ("puis", "y luego"),
    "from": ("depuis", "desde"),
    "trans": ("transition", "transición"),
    "tran": ("transition", "transición"),
    "notrans": ("sans transition", "sin transición"),
    "lookat": ("regarder", "mirar"),
    "old": ("ancien", "antiguo"),
    "none": ("tout droit", "recto"),
    "front": ("devant", "delante"),
    "move": ("bouger", "moverse"),
    "release": ("relâcher", "soltar"),
    "snap": ("claquer", "chasquear"),
    "flip": ("salto", "voltereta"),
    "sharp": ("vif", "brusco"),
    "wobble": ("tituber", "tambalearse"),
    "pose": ("pose", "pose"),
    "slump": ("s'affaisser", "desplomarse"),
    "zap": ("décharge", "descarga"),
    "cage": ("cage", "jaula"),
    "stone": ("pierre", "piedra"),
    "mace": ("masse", "maza"),
    "limp": ("boiter", "cojear"),
    "fire": ("feu", "fuego"),
    "write": ("écrire", "escribir"),
    "duck": ("se baisser", "agacharse"),
    "sweep": ("balayer", "barrer"),
    "panic": ("paniquer", "pánico"),
    "levitate": ("léviter", "levitar"),
    "delight": ("ravi", "encantado"),
    "annoyed": ("agacé", "molesto"),
    "smug": ("suffisant", "engreído"),
    "dreamy": ("rêveur", "soñador"),
    "sheepish": ("penaud", "avergonzado"),
    "sidestep": ("pas de côté", "paso lateral"),
    "scheming": ("comploter", "tramar"),
    "plot": ("comploter", "tramar"),
    "question": ("question", "pregunta"),
    "mirror": ("miroir", "espejo"),
    "tree": ("arbre", "árbol"),
    "flute": ("flûte", "flauta"),
    "play": ("jouer", "tocar"),
    "normal": ("normal", "normal"),
    "relief": ("soulagement", "alivio"),
    "sigh": ("soupirer", "suspirar"),
    "follow": ("suivre", "seguir"),
    "ground": ("au sol", "en el suelo"),
    "floor": ("au sol", "en el suelo"),
    "passout": ("perdre connaissance", "perder el conocimiento"),
    "passedout": ("sans connaissance", "inconsciente"),
    "adjust": ("ajuster", "ajustar"),
    "glasses": ("lunettes", "gafas"),
    "pour": ("verser", "verter"),
    "turban": ("turban", "turbante"),
    "bend": ("se pencher", "inclinarse"),
    "bent": ("penché", "inclinado"),
    "over": ("", ""),
    "celebration": ("célébrer", "celebrar"),
    "caught": ("attrapé", "atrapado"),
    "lesson": ("leçon", "lección"),
    "leg": ("jambe", "pierna"),
    "pat": ("tapoter", "palmear"),
    "dirt": ("la terre", "la tierra"),
    "scar": ("cicatrice", "cicatriz"),
    "shift": ("déplacer", "cambiar"),
    "weight": ("le poids", "el peso"),
    "warmup": ("s'échauffer", "calentar"),
    "hunched": ("voûté", "encorvado"),
    "bottom": ("en bas", "abajo"),
    "slip": ("glisser", "resbalar"),
    "declare": ("dire", "decir"),
    "overhand": ("par-dessus", "por encima"),
    "refill": ("remplir", "rellenar"),
    "away": ("s'éloigner", "alejarse"),
    "common": ("courant", "común"),
    "circular": ("en cercle", "en círculo"),
    "apex": ("sommet", "cumbre"),
    "collect": ("ramasser", "recoger"),
    "object": ("objet", "objeto"),
    "jellybeans": ("dragées", "grageas"),
    "rock": ("rocher", "roca"),
    "hole": ("trou", "agujero"),
    "human": ("humain", "humano"),
    "nipped": ("pincé", "pellizcado"),
    "full": ("complet", "completo"),
    "get": ("", ""),
    "in": ("dans", "en"),
    "out": ("dehors", "fuera"),
    "on": ("", ""),
    "go": ("aller", "ir"),
}

# Sorts et noms propres : tels quels, avec leur majuscule.
_TELS_QUELS = {
    "alohomora", "avifors", "diffindo", "expelliarmus", "flipendo", "fumos", "glacius",
    "incendio", "lapifors", "leviosa", "locomotormortis", "lumos", "mimblewimble",
    "mucusadnauseam", "patronus", "rictusempra", "spongify", "ron", "goyle", "hermione",
    "buckbeak", "bundi", "harry", "filch", "wingardium", "doxy", "ecto",
}

# Suites de mots qui n'en font qu'un.
_EXPRESSIONS: dict[tuple[str, ...], str] = {
    ("dont", "know"): "dunno",
    ("no", "trans"): "notrans",
    ("get", "up"): "getup",
    ("look", "at"): "lookat",
    ("pass", "out"): "passout",
}

_VISAGE = re.compile(
    r"^(mouth|eye|brow|blink)|^(ai|e|l|o|u|fv|mbp|wq|cdgknrsthyz|joy|angry|disgust|fear|sad|"
    r"smirk|squint|surprise)$", re.IGNORECASE)

_ANGLES = {"20", "24", "45", "90", "135", "160", "180"}
_CONNUS = set(_GLOSSAIRE) | _TELS_QUELS
# Dans un mot collé, pas de lettre seule : « trot » deviendrait « t r o t ».
_COLLABLES = {m for m in _CONNUS if len(m) > 1}
_ANGLAIS = {"l": "left", "r": "right", "pos": "positive", "neg": "negative", "trans": "transition",
            "tran": "transition", "rhand": "right hand", "lhand": "left hand",
            "notrans": "no transition", "dunno": "don't know", "getup": "get up",
            "lookat": "look at", "passout": "pass out", "passedout": "passed out"}


def _morceaux(nom: str) -> list[str]:
    """« WandCastFlipendo2 » → wand, cast, flipendo, 2 ; « Look_UpL45 » → look, up, l, 45."""
    nom = re.sub(r"([a-z])([A-Z])", r"\1 \2", nom)
    nom = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", nom)
    bruts = re.split(r"[\s_\-&]+|(?<=\D)(?=\d)|(?<=\d)(?=\D)", nom)
    return [b.lower() for b in bruts if b]


def _decouper(mot: str) -> list[str]:
    """Un mot collé (« talkleft », « transfromtalk ») en mots du glossaire, le
    moins de morceaux possible ; le mot tel quel si rien ne le couvre."""
    if mot in _CONNUS or mot.isdigit():
        return [mot]
    meilleur: list[list[str] | None] = [[]] + [None] * len(mot)
    for fin in range(1, len(mot) + 1):
        for debut in range(fin):
            gauche = meilleur[debut]
            if gauche is None or mot[debut:fin] not in _COLLABLES:
                continue
            essai = [*gauche, mot[debut:fin]]
            courant = meilleur[fin]
            if courant is None or len(essai) < len(courant):
                meilleur[fin] = essai
    trouve = meilleur[len(mot)]
    return trouve if trouve else [mot]


def _expressions(morceaux: list[str]) -> list[str]:
    sortie: list[str] = []
    i = 0
    while i < len(morceaux):
        for suite, mot in _EXPRESSIONS.items():
            if tuple(morceaux[i:i + len(suite)]) == suite:
                sortie.append(mot)
                i += len(suite)
                break
        else:
            sortie.append(morceaux[i])
            i += 1
    return sortie


def mots(nom: str) -> list[str]:
    return [m for brut in _morceaux(nom) for m in _decouper(brut)]


def libelle(nom: str, langue: str) -> str | None:
    """Le nom à montrer dans `langue` ; None pour un mouvement du visage."""
    if _VISAGE.search(nom):
        return None
    morceaux = _expressions(mots(nom))
    # « wand cast X » est le geste de lancer X.
    if morceaux[:2] == ["wand", "cast"] and len(morceaux) > 2:
        morceaux = morceaux[1:]
    colonne = {"fr": 0, "es": 1}.get(langue)
    sortie: list[str] = []
    for i, mot in enumerate(morceaux):
        suivant = morceaux[i + 1] if i + 1 < len(morceaux) else ""
        # « trans2talk », « land2run » : le 2 se lit « to ».
        if mot == "2" and i > 0 and suivant and not suivant.isdigit():
            mot = "to"
        if mot == "cast" and suivant in _TELS_QUELS:
            sortie.append({"fr": "lancer", "es": "lanzar"}.get(langue, "cast"))
        elif mot in _TELS_QUELS:
            sortie.append(mot.capitalize())
        elif mot in _ANGLES:
            sortie.append(f"{mot}°")
        elif colonne is not None and mot in _GLOSSAIRE:
            if _GLOSSAIRE[mot][colonne]:
                sortie.append(_GLOSSAIRE[mot][colonne])
        elif colonne is None and mot in _ANGLAIS:
            sortie.append(_ANGLAIS[mot])
        elif mot.isdigit():
            sortie.append(str(int(mot)))
        else:
            sortie.append(mot)
    # Le même mot deux fois de suite (« Sitting Sit ») : une seule fois.
    sans_doublon = [m for i, m in enumerate(sortie) if i == 0 or m != sortie[i - 1]]
    texte = " ".join(sans_doublon)
    return texte[:1].upper() + texte[1:]

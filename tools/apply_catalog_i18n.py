#!/usr/bin/env python
"""Injecte les blocs `i18n` dans un games.json à partir d'un dictionnaire FR → EN/ES.

Le catalogue porte ses propres traductions (voir `src.core.game_data._loc`) :
il se met à jour à distance, indépendamment des releases du launcher, donc un
jeu ajouté doit pouvoir arriver déjà traduit sans republier l'exécutable.

Usage :
    python tools/apply_catalog_i18n.py src/data/games.json
    python tools/apply_catalog_i18n.py ../accio-launcher-games/games.json

Le script est idempotent (rejouable sans dupliquer) et n'écrase jamais une
langue qu'il ne connaît pas. Il liste en sortie les chaînes françaises encore
sans traduction : c'est le rappel à chaque ajout de jeu ou de version.
"""

import json
import re
import sys
from pathlib import Path

# ── Titres officiels des jeux (recherche, pas traduction) ────────────────────
NAMES = {
    "Harry Potter à l'École des Sorciers": {
        "en": "Harry Potter and the Philosopher's Stone",
        "es": "Harry Potter y la piedra filosofal"},
    "Harry Potter et la Chambre des Secrets": {
        "en": "Harry Potter and the Chamber of Secrets",
        "es": "Harry Potter y la cámara secreta"},
    "Harry Potter et le Prisonnier d'Azkaban": {
        "en": "Harry Potter and the Prisoner of Azkaban",
        "es": "Harry Potter y el prisionero de Azkaban"},
    "Harry Potter et la Coupe de Feu": {
        "en": "Harry Potter and the Goblet of Fire",
        "es": "Harry Potter y el cáliz de fuego"},
    "Harry Potter et l'Ordre du Phénix": {
        "en": "Harry Potter and the Order of the Phoenix",
        "es": "Harry Potter y la Orden del Fénix"},
    "Harry Potter et le Prince de Sang-Mêlé": {
        "en": "Harry Potter and the Half-Blood Prince",
        "es": "Harry Potter y el misterio del príncipe"},
    "Harry Potter et les Reliques de la Mort — Partie 1": {
        "en": "Harry Potter and the Deathly Hallows — Part 1",
        "es": "Harry Potter y las reliquias de la Muerte — Parte 1"},
    "Harry Potter et les Reliques de la Mort — Partie 2": {
        "en": "Harry Potter and the Deathly Hallows — Part 2",
        "es": "Harry Potter y las reliquias de la Muerte — Parte 2"},
}

# ── Tags : vocabulaire fermé ─────────────────────────────────────────────────
TAGS = {
    "Action": {"en": "Action", "es": "Acción"},
    "Aventure": {"en": "Adventure", "es": "Aventura"},
    "Bataille": {"en": "Battle", "es": "Batalla"},
    "Combat": {"en": "Combat", "es": "Combate"},
    "Coopératif": {"en": "Co-op", "es": "Cooperativo"},
    "Duel": {"en": "Duels", "es": "Duelos"},
    "Exploration": {"en": "Exploration", "es": "Exploración"},
    "Infiltration": {"en": "Stealth", "es": "Sigilo"},
    "Monde ouvert": {"en": "Open world", "es": "Mundo abierto"},
    "Multi-personnages": {"en": "Multi-character", "es": "Multipersonaje"},
    "Plateforme": {"en": "Platformer", "es": "Plataformas"},
    "Potions": {"en": "Potions", "es": "Pociones"},
    "Quidditch": {"en": "Quidditch", "es": "Quidditch"},
    "TPS": {"en": "Third-person", "es": "Tercera persona"},
    "Énigmes": {"en": "Puzzles", "es": "Puzles"},
}

# ── Lignes de changelog ──────────────────────────────────────────────────────
CHANGES = {
    "Anti-aliasing 4x, filtrage anisotrope 8x": {
        "en": "4x anti-aliasing, 8x anisotropic filtering",
        "es": "Antialiasing 4x, filtrado anisotrópico 8x"},
    "Cap 100 FPS (limite UE1 recommandée)": {
        "en": "100 FPS cap (recommended UE1 limit)",
        "es": "Límite de 100 FPS (máximo recomendado en UE1)"},
    "Cap 100 FPS (stabilité du gameplay)": {
        "en": "100 FPS cap (gameplay stability)",
        "es": "Límite de 100 FPS (estabilidad del juego)"},
    "Cap 60 FPS intégré via DGVoodoo": {
        "en": "Built-in 60 FPS cap via DGVoodoo",
        "es": "Límite de 60 FPS integrado mediante DGVoodoo"},
    "Capture d'écran intégrée (F12) et prise en charge du DPI Windows (1440p natif)": {
        "en": "Built-in screenshot key (F12) and Windows DPI support (native 1440p)",
        "es": "Captura de pantalla integrada (F12) y compatibilidad con el DPI de "
              "Windows (1440p nativo)"},
    "Configuration par défaut optimisée": {
        "en": "Optimised default configuration",
        "es": "Configuración predeterminada optimizada"},
    "DGVoodoo 2.8 intégré": {
        "en": "DGVoodoo 2.8 bundled", "es": "DGVoodoo 2.8 integrado"},
    "DGVoodoo 2.8.1 intégré": {
        "en": "DGVoodoo 2.8.1 bundled", "es": "DGVoodoo 2.8.1 integrado"},
    "DGVoodoo 2.8.1 → 2.86.5": {
        "en": "DGVoodoo 2.8.1 → 2.86.5", "es": "DGVoodoo 2.8.1 → 2.86.5"},
    "Des images dans le menu des sauvegardes": {
        "en": "Thumbnails in the save game menu",
        "es": "Miniaturas en el menú de partidas guardadas"},
    "Fix crash sur Forêt Interdite, Lac, Labyrinthe et Voldemort": {
        "en": "Fixed crashes in the Forbidden Forest, the Lake, the Maze and the "
              "Voldemort fight",
        "es": "Corregidos los cierres en el Bosque Prohibido, el Lago, el Laberinto "
              "y el combate contra Voldemort"},
    "Interface mise à l'échelle pour les résolutions modernes": {
        "en": "UI scaled for modern resolutions",
        "es": "Interfaz escalada para resoluciones modernas"},
    "Latence d'entrée réduite, Alt+Tab instantané, correctif du doublon fantôme": {
        "en": "Reduced input latency, instant Alt+Tab, ghost duplicate fixed",
        "es": "Menor latencia de entrada, Alt+Tab instantáneo, corregido el "
              "duplicado fantasma"},
    "MSAA jusqu'à 16× avec repli automatique, FXAA et netteté adaptative": {
        "en": "MSAA up to 16× with automatic fallback, FXAA and adaptive sharpening",
        "es": "MSAA hasta 16× con repliegue automático, FXAA y nitidez adaptativa"},
    "Mode borderless windowed (alt-tab sans crash)": {
        "en": "Borderless windowed mode (crash-free alt-tab)",
        "es": "Modo ventana sin bordes (alt-tab sin cierres)"},
    "Nettoyage des fichiers inutiles (DRM, installeurs)": {
        "en": "Useless files removed (DRM, installers)",
        "es": "Archivos innecesarios eliminados (DRM, instaladores)"},
    "Nettoyage des fichiers inutiles (DRM, installeurs, manuel PDF)": {
        "en": "Useless files removed (DRM, installers, PDF manual)",
        "es": "Archivos innecesarios eliminados (DRM, instaladores, manual en PDF)"},
    "Nettoyage des fichiers inutiles (DRM, installeurs, support multilingue)": {
        "en": "Useless files removed (DRM, installers, multi-language support)",
        "es": "Archivos innecesarios eliminados (DRM, instaladores, soporte "
              "multiidioma)"},
    "Nettoyage des fichiers inutiles (~15 Mo)": {
        "en": "Useless files removed (~15 MB)",
        "es": "Archivos innecesarios eliminados (~15 MB)"},
    "Occlusion ambiante (SSAO), bloom et god rays volumétriques": {
        "en": "Ambient occlusion (SSAO), bloom and volumetric god rays",
        "es": "Oclusión ambiental (SSAO), bloom y rayos volumétricos"},
    "Renderer D3D11 1.6.2 intégré (antialiasing 8x, anisotropie 16x, bump mapping, "
    "SSAO, SSR)": {
        "en": "D3D11 renderer 1.6.2 bundled (8x anti-aliasing, 16x anisotropy, "
              "bump mapping, SSAO, SSR)",
        "es": "Renderizador D3D11 1.6.2 integrado (antialiasing 8x, anisotropía 16x, "
              "bump mapping, SSAO, SSR)"},
    "Renderer Kentie D3D11 intégré (antialiasing 4x, anisotropie 16x, bump mapping, "
    "SSAO, HDR, SSR)": {
        "en": "Kentie D3D11 renderer bundled (4x anti-aliasing, 16x anisotropy, "
              "bump mapping, SSAO, HDR, SSR)",
        "es": "Renderizador Kentie D3D11 integrado (antialiasing 4x, anisotropía 16x, "
              "bump mapping, SSAO, HDR, SSR)"},
    "SSAA optionnel (2×/3×/4×) et filtrage anisotrope forcé 16×": {
        "en": "Optional SSAA (2×/3×/4×) and forced 16× anisotropic filtering",
        "es": "SSAA opcional (2×/3×/4×) y filtrado anisotrópico forzado a 16×"},
    "VSync activé, upscaling Lanczos-2": {
        "en": "VSync enabled, Lanczos-2 upscaling",
        "es": "VSync activado, escalado Lanczos-2"},
    "Version originale du jeu": {
        "en": "Original game release", "es": "Versión original del juego"},
    "Vidéos d'intro adaptées au widescreen": {
        "en": "Intro videos adapted to widescreen",
        "es": "Vídeos de introducción adaptados a pantalla panorámica"},
    "Voix et textes FR + EN inclus": {
        "en": "French and English voices and text included",
        "es": "Voces y textos en francés e inglés incluidos"},
    "Voix et textes FR inclus": {
        "en": "French voices and text included",
        "es": "Voces y textos en francés incluidos"},
    "Widescreen 16:9 (1920x1080) avec FOV 106°": {
        "en": "16:9 widescreen (1920x1080) with 106° FOV",
        "es": "Panorámico 16:9 (1920x1080) con FOV de 106°"},
    "Widescreen 16:9 (1920x1080) avec FOV ajusté": {
        "en": "16:9 widescreen (1920x1080) with adjusted FOV",
        "es": "Panorámico 16:9 (1920x1080) con FOV ajustado"},
    "Wrapper D3D9 Chip-Biscuit intégré (widescreen 1920x1080, 100 FPS, 16:9)": {
        "en": "Chip-Biscuit D3D9 wrapper bundled (1920x1080 widescreen, 100 FPS, 16:9)",
        "es": "Wrapper D3D9 Chip-Biscuit integrado (panorámico 1920x1080, 100 FPS, 16:9)"},
    "Wrapper graphique D3D9 refondu (pipeline de post-traitement réglable)": {
        "en": "Rebuilt D3D9 graphics wrapper (tunable post-processing pipeline)",
        "es": "Wrapper gráfico D3D9 rediseñado (pipeline de posprocesado ajustable)"},
    "Étalonnage des couleurs : balance des blancs, contraste ciné, split-tone, vignette": {
        "en": "Colour grading: white balance, cinematic contrast, split-tone, vignette",
        "es": "Etalonaje de color: balance de blancos, contraste cinematográfico, "
              "split-tone, viñeta"},
}

# ── Descriptions ─────────────────────────────────────────────────────────────
DESCRIPTIONS = {
    "Incarnez Harry Potter et découvrez l'univers magique de Poudlard pour la toute "
    "première fois. Explorez les couloirs du château, apprenez des sortilèges, préparez "
    "des potions et découvrez des passages secrets tout en suivant l'intrigue du premier "
    "livre. Participez à des matchs de Quidditch effrénés et affrontez des créatures "
    "magiques dans cette aventure inoubliable.": {
        "en": "Step into Harry Potter's shoes and discover the magical world of Hogwarts "
              "for the very first time. Explore the castle corridors, learn spells, brew "
              "potions and uncover secret passages as you follow the story of the first "
              "book. Take part in frantic Quidditch matches and face magical creatures in "
              "this unforgettable adventure.",
        "es": "Ponte en la piel de Harry Potter y descubre el mundo mágico de Hogwarts por "
              "primera vez. Explora los pasillos del castillo, aprende hechizos, prepara "
              "pociones y encuentra pasadizos secretos mientras sigues la trama del primer "
              "libro. Participa en frenéticos partidos de quidditch y enfréntate a "
              "criaturas mágicas en esta aventura inolvidable."},
    "Replongez dans le monde des sorciers avec un Poudlard plus ouvert et plus riche à "
    "explorer que jamais. Apprenez de nouveaux sortilèges comme Expelliarmus et Lumos "
    "pour résoudre des énigmes et vaincre vos ennemis. Entre les matchs de Quidditch, les "
    "infiltrations sous la Cape d'Invisibilité et l'exploration de la Forêt Interdite, "
    "chaque recoin du château regorge de secrets à découvrir.": {
        "en": "Dive back into the wizarding world with a Hogwarts more open and richer to "
              "explore than ever. Learn new spells such as Expelliarmus and Lumos to solve "
              "puzzles and defeat your enemies. Between Quidditch matches, sneaking around "
              "under the Invisibility Cloak and exploring the Forbidden Forest, every "
              "corner of the castle is packed with secrets to uncover.",
        "es": "Vuelve al mundo mágico con un Hogwarts más abierto y rico de explorar que "
              "nunca. Aprende nuevos hechizos como Expelliarmus y Lumos para resolver "
              "enigmas y derrotar a tus enemigos. Entre partidos de quidditch, "
              "infiltraciones bajo la capa invisible y expediciones al Bosque Prohibido, "
              "cada rincón del castillo esconde secretos por descubrir."},
    "Pour la première fois, incarnez non seulement Harry, mais aussi Ron et Hermione, "
    "chacun disposant de capacités et sortilèges uniques. Explorez librement Poudlard et "
    "ses alentours, résolvez des énigmes en alternant entre les trois personnages et "
    "envolez-vous à dos d'Hippogriffe. Avec ses quêtes secondaires et ses combats "
    "magiques, cette aventure offre une expérience riche et variée.": {
        "en": "For the first time, play not only as Harry but also as Ron and Hermione, "
              "each with their own abilities and spells. Roam Hogwarts and its grounds "
              "freely, solve puzzles by switching between the three characters and take to "
              "the skies on a Hippogriff. With its side quests and magical duels, this "
              "adventure offers a rich and varied experience.",
        "es": "Por primera vez no solo controlas a Harry, sino también a Ron y Hermione, "
              "cada uno con habilidades y hechizos propios. Recorre Hogwarts y sus "
              "alrededores con libertad, resuelve enigmas alternando entre los tres "
              "personajes y surca el cielo a lomos de un hipogrifo. Con sus misiones "
              "secundarias y sus combates mágicos, esta aventura ofrece una experiencia "
              "rica y variada."},
    "Affrontez les épreuves du Tournoi des Trois Sorciers en incarnant Harry, Ron ou "
    "Hermione dans cette aventure d'action coopérative. Lancez des sortilèges puissants, "
    "combattez des créatures redoutables et relevez les trois tâches mortelles du tournoi "
    "jusqu'à l'ultime confrontation avec Lord Voldemort. Jouez en coopération avec "
    "jusqu'à deux amis pour la première fois dans la série.": {
        "en": "Take on the Triwizard Tournament as Harry, Ron or Hermione in this "
              "co-operative action adventure. Cast powerful spells, fight fearsome "
              "creatures and face the tournament's three deadly tasks all the way to the "
              "final confrontation with Lord Voldemort. Play co-operatively with up to two "
              "friends for the first time in the series.",
        "es": "Afronta las pruebas del Torneo de los Tres Magos encarnando a Harry, Ron o "
              "Hermione en esta aventura de acción cooperativa. Lanza hechizos poderosos, "
              "combate criaturas temibles y supera las tres pruebas mortales del torneo "
              "hasta el enfrentamiento final con lord Voldemort. Juega en cooperativo con "
              "hasta dos amigos por primera vez en la saga."},
    "Explorez une reconstitution complète et détaillée de Poudlard en monde ouvert, sans "
    "aucun écran de chargement, dans l'aventure la plus immersive de la série. Recrutez "
    "des membres pour l'Armée de Dumbledore, affrontez les Serpentard en duels de "
    "sorciers et interagissez avec l'ensemble du château grâce à vos sortilèges. "
    "Découvrez chaque recoin de l'école tout en accomplissant les missions inspirées du "
    "livre et du film.": {
        "en": "Explore a complete and detailed recreation of Hogwarts as an open world, "
              "with no loading screens at all, in the most immersive adventure of the "
              "series. Recruit members for Dumbledore's Army, face Slytherins in wizard "
              "duels and interact with the whole castle through your spells. Discover every "
              "corner of the school while carrying out missions inspired by the book and "
              "the film.",
        "es": "Explora una recreación completa y detallada de Hogwarts en mundo abierto, "
              "sin una sola pantalla de carga, en la aventura más inmersiva de la saga. "
              "Recluta miembros para el Ejército de Dumbledore, enfréntate a los Slytherin "
              "en duelos de magos e interactúa con todo el castillo gracias a tus "
              "hechizos. Descubre cada rincón del colegio mientras cumples las misiones "
              "inspiradas en el libro y la película."},
    "Parcourez une fois de plus les couloirs de Poudlard dans cette aventure d'action qui "
    "met l'accent sur les duels de sorciers, la préparation de potions et le Quidditch. "
    "Affrontez vos adversaires dans des combats magiques intenses, perfectionnez vos "
    "talents de potioniste et menez l'équipe de Gryffondor à la victoire. Explorez le "
    "château à différents moments de la journée et percez les mystères qui entourent le "
    "Prince de Sang-Mêlé.": {
        "en": "Walk the corridors of Hogwarts once more in this action adventure built "
              "around wizard duels, potion brewing and Quidditch. Face your opponents in "
              "intense magical fights, hone your skills as a potioneer and lead the "
              "Gryffindor team to victory. Explore the castle at different times of day and "
              "unravel the mystery surrounding the Half-Blood Prince.",
        "es": "Recorre una vez más los pasillos de Hogwarts en esta aventura de acción "
              "centrada en los duelos de magos, la preparación de pociones y el quidditch. "
              "Enfréntate a tus rivales en intensos combates mágicos, perfecciona tu "
              "talento con el caldero y lleva al equipo de Gryffindor a la victoria. "
              "Explora el castillo a distintas horas del día y desvela los misterios que "
              "rodean al Príncipe Mestizo."},
    "Plongez dans l'aventure la plus sombre de la saga. Harry, Ron et Hermione ont quitté "
    "Poudlard pour traquer et détruire les Horcruxes de Voldemort. Affrontez des Rafleurs "
    "et des Mangemorts dans des combats intenses à la troisième personne, infiltrez le "
    "Ministère de la Magie et survivez dans des environnements hostiles. Avec son gameplay "
    "orienté action et ses missions furtives, ce jeu vous place au cœur d'une guerre où "
    "chaque sortilège compte.": {
        "en": "Step into the darkest chapter of the saga. Harry, Ron and Hermione have left "
              "Hogwarts to hunt down and destroy Voldemort's Horcruxes. Fight Snatchers and "
              "Death Eaters in intense third-person combat, infiltrate the Ministry of "
              "Magic and survive in hostile territory. With its action-driven gameplay and "
              "stealth missions, this game puts you at the heart of a war where every spell "
              "counts.",
        "es": "Adéntrate en el capítulo más oscuro de la saga. Harry, Ron y Hermione han "
              "dejado Hogwarts para buscar y destruir los Horrocruxes de Voldemort. Combate "
              "contra carroñeros y mortífagos en intensos enfrentamientos en tercera "
              "persona, infíltrate en el Ministerio de Magia y sobrevive en territorio "
              "hostil. Con su jugabilidad orientada a la acción y sus misiones de sigilo, "
              "este juego te sitúa en el corazón de una guerra donde cada hechizo cuenta."},
    "L'ultime bataille pour Poudlard. Incarnez Harry et ses alliés dans un jeu d'action "
    "explosif centré sur la Bataille de Poudlard. Enchaînez les sortilèges offensifs et "
    "défensifs dans des affrontements spectaculaires, protégez le château contre les "
    "forces de Voldemort et menez le combat final. Avec ses combats à couvert, ses duels "
    "de baguettes intenses et ses moments cinématiques, cette conclusion épique met un "
    "point final à la saga vidéoludique Harry Potter.": {
        "en": "The final battle for Hogwarts. Play as Harry and his allies in an explosive "
              "action game centred on the Battle of Hogwarts. Chain offensive and defensive "
              "spells in spectacular clashes, defend the castle against Voldemort's forces "
              "and lead the last stand. With its cover-based combat, intense wand duels and "
              "cinematic set pieces, this epic conclusion closes the Harry Potter game "
              "saga.",
        "es": "La batalla final por Hogwarts. Encarna a Harry y a sus aliados en un "
              "explosivo juego de acción centrado en la Batalla de Hogwarts. Encadena "
              "hechizos ofensivos y defensivos en enfrentamientos espectaculares, protege "
              "el castillo de las fuerzas de Voldemort y lidera el combate final. Con sus "
              "coberturas, sus intensos duelos de varitas y sus momentos cinematográficos, "
              "esta conclusión épica pone el punto final a la saga de videojuegos de Harry "
              "Potter."},
}

LANGS = ("en", "es")


def _merge(target: dict, lang: str, key: str, value) -> None:
    """Pose `value` dans target["i18n"][lang][key] sans écraser les autres langues."""
    block = target.setdefault("i18n", {})
    if not isinstance(block, dict):
        block = {}
        target["i18n"] = block
    block.setdefault(lang, {})[key] = value


def apply(catalog: dict) -> list[str]:
    """Injecte les traductions connues. Retourne les chaînes FR non traduites."""
    missing: list[str] = []

    def lookup(table: dict, text: str) -> dict | None:
        entry = table.get(text)
        if entry is None and text not in missing:
            missing.append(text)
        return entry

    for game in catalog.get("games", []):
        for lang in LANGS:
            name = lookup(NAMES, game.get("name", ""))
            if name:
                _merge(game, lang, "name", name[lang])
            desc = lookup(DESCRIPTIONS, game.get("description", ""))
            if desc:
                _merge(game, lang, "description", desc[lang])
            tags = game.get("tags", [])
            translated = [lookup(TAGS, t) for t in tags]
            if tags and all(t is not None for t in translated):
                _merge(game, lang, "tags", [t[lang] for t in translated])
        for version in game.get("versions", []):
            changes = version.get("changes", [])
            translated = [lookup(CHANGES, c) for c in changes]
            if changes and all(c is not None for c in translated):
                for lang in LANGS:
                    _merge(version, lang, "changes", [c[lang] for c in translated])

    return missing


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    path = Path(argv[1])
    with open(path, encoding="utf-8", newline="") as f:
        raw = f.read()
    # On réécrit avec la MISE EN FORME du fichier reçu (fins de ligne et
    # indentation). Le dépôt du catalogue est en CRLF indenté à 4 espaces :
    # réécrire en LF/2 espaces reformate les 431 lignes existantes et noie les
    # vraies modifications dans un diff illisible.
    newline = "\r\n" if "\r\n" in raw else "\n"
    indent_match = re.search(r'^([ \t]+)"', raw, re.MULTILINE)
    indent = len(indent_match.group(1)) if indent_match else 2
    catalog = json.loads(raw)
    missing = apply(catalog)
    # ensure_ascii=False est OBLIGATOIRE : sinon les accents (et demain le CJK)
    # partent en \uXXXX et le fichier devient illisible en revue de PR.
    with open(path, "w", encoding="utf-8", newline=newline) as f:
        f.write(json.dumps(catalog, ensure_ascii=False, indent=indent) + "\n")
    print(f"{path} : {len(catalog.get('games', []))} jeux traités")
    if missing:
        print(f"\n{len(missing)} chaîne(s) sans traduction — à ajouter dans ce script :")
        for text in missing:
            print(f"  · {text}")
        return 1
    print("Toutes les chaînes sont traduites.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

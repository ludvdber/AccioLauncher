# 🌍 Traducteurs

Accio Launcher parle plusieurs langues grâce aux personnes ci-dessous.
**Merci à elles** — une traduction, c'est ce qui permet à quelqu'un de
découvrir le launcher dans sa propre langue.

| Langue | Code | Traduit par |
|--------|:----:|-------------|
| Français *(langue source)* | `fr` | ASTeam |
| English | `en` | ASTeam |
| Español | `es` | ASTeam |

Ces crédits sont aussi affichés dans le launcher, dans **Paramètres → À propos**.
Ils sont lus directement depuis le bloc `_meta.translators` de chaque fichier de
langue : en vous ajoutant dans votre traduction, vous apparaissez automatiquement
dans les deux endroits.

---

## Ajouter une langue

Tout se passe dans des fichiers de données. **Aucune ligne de Python à écrire.**

### 1. Partez de l'anglais

Copiez [`src/data/i18n/en.json`](src/data/i18n/en.json) sous le code de votre
langue — `de.json` pour l'allemand, `pt.json` pour le portugais, `ja.json` pour
le japonais… (codes [ISO 639-1](https://fr.wikipedia.org/wiki/Liste_des_codes_ISO_639-1)).

### 2. Remplissez

Le fichier a deux blocs. Dans `_meta`, mettez votre code, le nom de la langue
**écrit dans cette langue**, votre pseudo, et le séparateur décimal de votre
langue :

```json
{
  "_meta": {
    "code": "de",
    "name": "Deutsch",
    "translators": ["VotrePseudo"],
    "decimal": ","
  },
  "strings": {
    "Fermer": "Schließen",
    "Espace libre : {}": "Freier Speicher: {}"
  }
}
```

`decimal` vaut `","` ou `"."`. C'est ce qui sépare les décimales d'un poids ou
d'une vitesse : « 4,6 Go » en français et en allemand, « 4.6 GB » en anglais.
Le champ est facultatif — sans lui vous aurez la virgule, qui est le cas le
plus répandu — et toute autre valeur est ignorée.

Dans `strings`, **les clés sont les chaînes françaises et ne doivent jamais
être modifiées** — ce sont elles qui identifient chaque texte. Vous ne changez
que les valeurs, à droite.

Trois règles, et c'est tout :

- **Gardez les `{}`.** Ce sont des trous que le launcher remplit à l'exécution.
  `"Espace libre : {}"` doit rester une phrase avec exactement un `{}`, sinon
  l'affichage plante. Vous pouvez en revanche les déplacer dans la phrase.
- **Gardez les `\n`.** Ce sont des retours à la ligne.
- **Enregistrez en UTF-8**, sans échapper les accents en `\uXXXX` (votre éditeur
  le fait tout seul ; c'est juste pour que le fichier reste lisible en revue).

Une traduction **incomplète est acceptée**. Ce qui manque retombe sur l'anglais,
puis sur le français — jamais sur du vide. Traduisez ce que vous pouvez, on
complétera.

### 3. Testez sans rien installer

Déposez votre fichier dans :

```
%USERPROFILE%\Games\AccioLauncher\i18n\de.json
```

Relancez le launcher : votre langue apparaît dans **Paramètres → Langue**.
Le dossier utilisateur est fusionné **par-dessus** les traductions embarquées,
donc vous voyez immédiatement vos modifications, sans attendre ni build ni
release. Vous pouvez itérer autant que vous voulez.

### 4. Traduisez le catalogue *(optionnel)*

Les noms des jeux, leurs descriptions, leurs tags et les changelogs vivent dans
le catalogue et non dans l'interface. Ils se traduisent dans
[`tools/apply_catalog_i18n.py`](tools/apply_catalog_i18n.py), qui contient un
dictionnaire par type de contenu. Le script signale les chaînes non traduites,
donc rien ne se perd en silence.

C'est un bonus : une traduction de l'interface seule est déjà très utile.

### 5. Proposez-la

Ouvrez une [Pull Request](https://github.com/ludvdber/AccioLauncher/pulls) avec
votre fichier, ou passez simplement par le [Discord](https://discord.gg/TNwDQd7KGe)
si vous préférez — je m'occupe du reste.

Votre fichier ne touche que votre langue : il n'entre en conflit avec aucune
autre contribution.

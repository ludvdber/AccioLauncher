import QtQuick

// Le jumeau visuel de la fiche (`src/ui/fiche_gpu.py`) : les vrais widgets restent
// la seule source de vérité (texte, mise en page, focus, clics) mais ne se peignent
// plus ; chacun envoie ici sa propre image, une fois, à chaque changement réel.
// Un nœud = une image posée à la place du widget ; la scène ne fait que composer.
// Trois groupes : le bloc fixe de la fiche, sa zone défilante, la barre audio.
Item {
    id: jumeau
    objectName: "ficheJumeau"
    anchors.fill: parent

    property rect zoneDefilante: Qt.rect(0, 0, 0, 0)
    property var _noeuds: ({})

    function _groupe(nom) {
        return nom === "contenu" ? contenu : nom === "audio" ? audio : fiche
    }

    // Reçoit un lot de changements : seules les propriétés qui ont changé y sont.
    function poser(lot) {
        for (var i = 0; i < lot.length; ++i) {
            var e = lot[i]
            var n = _noeuds[e.cle]
            if (!n) {
                n = modele.createObject(_groupe(e.groupe))
                _noeuds[e.cle] = n
            }
            for (var k in e)
                if (k !== "cle" && k !== "groupe") n[k] = e[k]
        }
    }

    function oublier(cles) {
        for (var i = 0; i < cles.length; ++i) {
            var n = _noeuds[cles[i]]
            if (n) n.destroy()
            delete _noeuds[cles[i]]
        }
    }

    // Tests et diagnostic : le nœud d'un widget, ses propriétés lues côté scène.
    function etatDe(cle) {
        var n = _noeuds[cle]
        return n ? { "x": n.x, "y": n.y, "visible": n.visible, "source": n.source.toString(),
                     "width": n.width, "height": n.height } : null
    }
    function nombre() { return Object.keys(_noeuds).length }

    // Le fondu de la fiche au changement de jeu (500 ms, OutCubic) : l'animation de
    // scène remplace le `QGraphicsOpacityEffect` du chemin QPainter.
    function fonduZero() {
        fondu.stop()
        fiche.opacity = 0
    }
    function fonduEntree(duree) {
        fondu.stop()
        fondu.duration = duree
        fiche.opacity = 0
        fondu.start()
    }

    NumberAnimation {
        id: fondu
        target: fiche
        property: "opacity"
        from: 0
        to: 1
        easing.type: Easing.OutCubic
    }

    Component {
        id: modele
        Image {
            smooth: true
            mipmap: false
            cache: false
            asynchronous: false
            fillMode: Image.Stretch
        }
    }

    Item {
        id: fiche
        objectName: "ficheFondu"
        anchors.fill: parent
        // Le contenu défilant : rogné à la vue ; ses nœuds sont posés relativement à elle.
        Item {
            id: contenu
            x: jumeau.zoneDefilante.x
            y: jumeau.zoneDefilante.y
            width: jumeau.zoneDefilante.width
            height: jumeau.zoneDefilante.height
            clip: true
        }
    }

    // Hors du fondu de la fiche, comme la barre sur le chemin des widgets.
    Item {
        id: audio
        anchors.fill: parent
    }
}

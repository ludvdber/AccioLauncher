import QtQuick
import QtMultimedia

// Le fond de l'accueil, dessiné par la carte graphique (`src/ui/fond_gpu.py`).
// Même rendu que `BackgroundWidget` : illustration en « cover » zoomée et
// décalée par la parallaxe, ou bandeau étendu ; bande-annonce ; voile ; voiles
// fixes (une image peinte par Python, `construire_voiles`) ; débord du bas.
// Tout ce qui bouge ici est animé par Python (opacité, zoom, parallaxe) : la
// scène ne redessine que quand une valeur change.
Item {
    id: racine

    property url source
    property url ancienne              // sous-couche du fondu enchaîné, figée au clic :
    property real ancienneZoom: 1.0
    property real ancienneParallaxeX: 0
    property real ancienneParallaxeY: 0
    property bool ancienneEtendu: false
    property real opacite: 1.0
    property real zoom: 1.0
    property real parallaxeX: 0        // décalage courant, en pixels logiques
    property real parallaxeY: 0
    property bool cinema: false
    property bool video: false
    property url voiles
    property color fond: "#060611"
    property real voileAlpha: 38 / 255
    property real debord: 2
    property real parallaxeMaxX: 20
    property real parallaxeMaxY: 12
    // Fond étendu (voir `fond_gpu._doit_etendre`) : décidé par Python, qui connaît
    // la taille de l'image et l'échelle de l'écran.
    property bool etendu: false
    property real etenduMarge: 1.06
    property real etenduFondu: 0.32
    property real etenduVoileFlou: 100 / 255
    property int etenduBandes: 48

    readonly property alias sortieVideo: sortie

    Rectangle { anchors.fill: parent; color: racine.fond }

    // ── L'illustration : en « cover » (zoom ×1,08 de base, puis le zoom d'arrivée),
    // ou bandeau étendu (`BackgroundWidget._peindre_etendu`). Un composant, parce
    // que la sous-couche du fondu doit être LA MÊME image, figée où elle était.
    component Couche: Item {
        id: couche
        property url src
        property real zoomC: 1.0
        property real px: 0
        property real py: 0
        property bool etenduC: false
        property bool sync: false        // la sous-couche : déjà en cache, sans attente
        anchors.fill: parent

        Image {
            visible: !couche.etenduC
            width: parent.width * 1.08 * couche.zoomC
            height: parent.height * 1.08 * couche.zoomC
            x: (parent.width - width) / 2 + couche.px
            y: (parent.height - height) / 2 + couche.py
            source: couche.etenduC ? "" : couche.src
            fillMode: Image.PreserveAspectCrop
            asynchronous: !couche.sync; smooth: true; mipmap: true
        }

        // Bandeau étendu : la copie floue plein cadre, en retrait, puis l'image nette
        // en haut, dont le bas s'efface dedans.
        Item {
            anchors.fill: parent
            visible: couche.etenduC
            // Le flou : une copie minuscule agrandie deux fois en lissage (texture
            // du calque au quart, puis plein cadre), comme le chemin QPainter.
            Item {
                x: -racine.parallaxeMaxX + couche.px * 0.5
                y: -racine.parallaxeMaxY + couche.py * 0.5
                width: parent.width + 2 * racine.parallaxeMaxX
                height: parent.height + 2 * racine.parallaxeMaxY
                layer.enabled: couche.etenduC
                layer.textureSize: Qt.size(Math.max(1, Math.round(couche.width / 4)), Math.max(1, Math.round(couche.height / 4)))
                layer.smooth: true
                Image {
                    anchors.fill: parent
                    source: couche.etenduC ? couche.src : ""
                    sourceSize: Qt.size(Math.max(1, Math.round(couche.width / 24)), Math.max(1, Math.round(couche.height / 24)))
                    fillMode: Image.Stretch
                    asynchronous: !couche.sync; smooth: true
                }
            }
            // En retrait : en grand écran, le bas de l'image y revenait en « fantôme ».
            Rectangle { anchors.fill: parent; color: Qt.rgba(racine.fond.r, racine.fond.g, racine.fond.b, racine.etenduVoileFlou) }
            Item {
                id: bandeau
                width: parent.width * racine.etenduMarge * couche.zoomC
                height: net.implicitWidth > 0 ? width * net.implicitHeight / net.implicitWidth : 0
                x: (parent.width - width) / 2 + couche.px
                y: -racine.parallaxeMaxY + couche.py
                // Le haut, opaque ; texture chargée une fois, partagée par les bandes.
                Item {
                    width: parent.width; height: parent.height * (1 - racine.etenduFondu)
                    clip: true
                    Image {
                        id: net
                        width: bandeau.width; height: bandeau.height
                        source: couche.etenduC ? couche.src : ""
                        fillMode: Image.Stretch
                        asynchronous: !couche.sync; smooth: true; mipmap: true
                    }
                }
                // Le bas s'efface en bandes fines d'opacité décroissante (rognées par
                // le GPU, même texture) : le flou se voit dessous, comme le masque
                // `DestinationIn` du chemin QPainter.
                Repeater {
                    model: couche.etenduC ? racine.etenduBandes : 0
                    Item {
                        required property int index
                        readonly property real haut: bandeau.height * (1 - racine.etenduFondu)
                        readonly property real pas: bandeau.height * racine.etenduFondu / racine.etenduBandes
                        y: haut + index * pas
                        width: bandeau.width; height: Math.ceil(pas) + 1
                        clip: true
                        opacity: 1 - (index + 0.5) / racine.etenduBandes
                        Image {
                            y: -parent.y
                            width: bandeau.width; height: bandeau.height
                            source: net.source
                            fillMode: Image.Stretch
                            asynchronous: !couche.sync; smooth: true; mipmap: true
                        }
                    }
                }
            }
        }
    }

    // Sous-couche du fondu : l'ancienne illustration FIGÉE là où elle était au clic
    // (zoom, parallaxe, cadrage, voile), comme la capture `grab()` du chemin QPainter.
    // Sans cela, elle reprenait sa place de départ, plus claire, avant le jeu suivant.
    Item {
        anchors.fill: parent
        visible: racine.opacite < 0.999 && racine.ancienne.toString() !== ""
        Couche {
            src: racine.ancienne
            zoomC: racine.ancienneZoom
            px: racine.ancienneParallaxeX
            py: racine.ancienneParallaxeY
            etenduC: racine.ancienneEtendu
            sync: true
        }
        Rectangle { anchors.fill: parent; visible: !racine.cinema; color: Qt.rgba(0, 0, 0, racine.voileAlpha) }
    }

    Item {
        id: plan
        anchors.fill: parent
        opacity: racine.opacite

        Couche {
            src: racine.source
            zoomC: racine.zoom
            px: racine.parallaxeX
            py: racine.parallaxeY
            etenduC: racine.etendu
        }

        // ── Bande-annonce : les images arrivent de la carte graphique, sans détour ──
        VideoOutput {
            id: sortie
            objectName: "sortieVideo"
            anchors.fill: parent
            visible: racine.video
            fillMode: VideoOutput.PreserveAspectCrop
        }

        Rectangle { anchors.fill: parent; visible: !racine.cinema; color: Qt.rgba(0, 0, 0, racine.voileAlpha) }
    }

    // Voiles fixes, à pleine opacité même pendant le fondu (comme `BackgroundWidget`).
    Image {
        anchors.fill: parent
        visible: !racine.cinema && racine.voiles.toString() !== ""
        source: racine.voiles
        cache: false
        smooth: true
    }
    // Débord du bas : atteindre le pixel physique aux échelles fractionnaires.
    Rectangle {
        visible: !racine.cinema
        y: parent.height - racine.debord; width: parent.width; height: racine.debord * 2
        color: racine.fond
    }

    // ── Particules (`fond_gpu.ParticulesGPU`) ──
    // Chaque particule est une FONCTION du temps : position, oscillation, retour
    // par l'autre bord, scintillement et rotation se déduisent du nombre de pas
    // écoulés (`temps`, posé par Python au rythme du Ticker), sans simulation.
    // Mêmes formules que `ParticleOverlay._advance` et `paintEvent`.
    property var particules: []
    property real temps: 0            // en pas du Ticker
    property real secondesParPas: 0.033
    property bool particulesVisibles: true

    function _mod(a, n) { return ((a % n) + n) % n }
    // Hasard reproductible : la nouvelle abscisse d'une particule revenue par l'autre bord.
    function _hasard(i, k) { var s = Math.sin(i * 12.9898 + k * 78.233) * 43758.5453; return s - Math.floor(s) }

    // Une seule boucle par pas, qui pose x, y, opacité et rotation : des liaisons par
    // particule (une douzaine chacune) coûtaient 0,6 ms de JavaScript à chaque pas.
    onTempsChanged: _poserParticules()
    function _poserParticules() {
        var n = temps, w = width, h = height, cycle = h + 30
        for (var i = 0; i < repetition.count; ++i) {
            var it = repetition.itemAt(i)
            if (!it) continue
            var p = it.p
            var yBrut = p.y0 + p.vy * n
            var tour = Math.floor((yBrut + 20) / cycle)
            var phase = p.phase0 + p.ps * n
            // Somme des sin(phase) pas à pas ≈ son intégrale : l'oscillation en forme fermée.
            var osc = p.ps !== 0 ? p.sway * (Math.cos(p.phase0) - Math.cos(phase)) / p.ps : 0
            var xBrut = p.x0 + p.vx * n + osc + (tour !== 0 ? _hasard(i, tour) * w : 0)
            it.x = -20 + _mod(xBrut + 20, w + 40)
            it.y = -20 + _mod(yBrut + 20, cycle)
            it.opacity = Math.max(0.05, Math.min(0.55, p.base + Math.sin(n * secondesParPas * p.flicker + phase) * p.variation))
            if (p.rs !== 0) it.angle = p.rot0 + p.rs * n
        }
    }

    Item {
        anchors.fill: parent
        visible: racine.particulesVisibles && !racine.cinema
        Repeater {
            id: repetition
            model: racine.particules
            onItemAdded: racine._poserParticules()
            Item {
                required property var modelData
                readonly property var p: modelData
                property real angle: p.rot0
                // Le halo à 30 % de l'opacité de la particule (`paintEvent`).
                Image {
                    visible: parent.p.glow > 0
                    source: visible ? "image://accio/halo/" + parent.p.rgb : ""
                    width: parent.p.glow * 2; height: width
                    x: -width / 2; y: -height / 2
                    opacity: 0.30
                    smooth: true
                }
                Rectangle {
                    visible: parent.p.forme === "point"
                    width: parent.p.size * 2; height: width; radius: width / 2
                    x: -parent.p.size; y: -parent.p.size
                    color: Qt.rgba(parent.p.r, parent.p.g, parent.p.b, 1)
                    antialiasing: true
                }
                Image {
                    visible: parent.p.forme !== "point"
                    source: visible ? "image://accio/forme/" + parent.p.forme + "/" + parent.p.rgb + "/" + parent.p.size.toFixed(2) : ""
                    width: parent.p.size * 2.4; height: width
                    x: -width / 2; y: -height / 2
                    rotation: parent.angle
                    smooth: true
                }
            }
        }
    }
}

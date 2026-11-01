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
    property url ancienne              // sous-couche du fondu enchaîné
    property real opacite: 1.0
    property real zoom: 1.0
    property real parallaxeX: 0        // décalage courant, en pixels logiques
    property real parallaxeY: 0
    property bool cinema: false
    property bool video: false
    property url voiles
    property color fond: "#060611"
    property color ambiance: "#0b0d1e"
    property real voileAlpha: 38 / 255
    property real debord: 2
    property real parallaxeMaxY: 12
    // Fond étendu (voir `fond_gpu._doit_etendre`) : décidé par Python, qui connaît
    // la taille de l'image et l'échelle de l'écran.
    property bool etendu: false
    property real etenduMarge: 1.06
    property real etenduFondu: 0.32

    readonly property alias sortieVideo: sortie

    Rectangle { anchors.fill: parent; color: racine.fond }

    // Sous-couche du fondu : l'ancienne illustration, immobile.
    Image {
        anchors.fill: parent
        visible: racine.opacite < 0.999 && racine.ancienne.toString() !== ""
        source: racine.ancienne
        fillMode: Image.PreserveAspectCrop
        asynchronous: true; smooth: true; mipmap: true
    }

    Item {
        id: plan
        anchors.fill: parent
        opacity: racine.opacite

        // ── Illustration en « cover » : zoom ×1,08 de base, puis le zoom d'arrivée ──
        Image {
            id: couverture
            visible: !racine.etendu
            width: parent.width * 1.08 * racine.zoom
            height: parent.height * 1.08 * racine.zoom
            x: (parent.width - width) / 2 + racine.parallaxeX
            y: (parent.height - height) / 2 + racine.parallaxeY
            source: racine.etendu ? "" : racine.source
            fillMode: Image.PreserveAspectCrop
            asynchronous: true; smooth: true; mipmap: true
        }

        // ── Bandeau étendu : net en haut, ancré en haut, fondu dans sa propre couleur ──
        Item {
            anchors.fill: parent
            visible: racine.etendu
            Rectangle { anchors.fill: parent; color: racine.ambiance }
            Item {
                id: bandeau
                width: parent.width * racine.etenduMarge * racine.zoom
                height: net.implicitWidth > 0 ? width * net.implicitHeight / net.implicitWidth : 0
                x: (parent.width - width) / 2 + racine.parallaxeX
                y: -racine.parallaxeMaxY + racine.parallaxeY
                Image {
                    id: net
                    anchors.fill: parent
                    source: racine.etendu ? racine.source : ""
                    fillMode: Image.Stretch
                    asynchronous: true; smooth: true; mipmap: true
                }
                Rectangle {
                    y: parent.height * (1 - racine.etenduFondu)
                    width: parent.width; height: parent.height * racine.etenduFondu + 1
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: Qt.rgba(racine.ambiance.r, racine.ambiance.g, racine.ambiance.b, 0) }
                        GradientStop { position: 1.0; color: racine.ambiance }
                    }
                }
            }
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

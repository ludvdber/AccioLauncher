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

    Item {
        anchors.fill: parent
        visible: racine.particulesVisibles && !racine.cinema
        Repeater {
            model: racine.particules
            Item {
                id: part
                required property var modelData
                required property int index
                readonly property var p: modelData
                readonly property real n: racine.temps
                readonly property real hauteurCycle: racine.height + 30
                readonly property real yBrut: p.y0 + p.vy * n
                readonly property real tour: Math.floor((yBrut + 20) / hauteurCycle)
                readonly property real phase: p.phase0 + p.ps * n
                // Somme des sin(phase) pas à pas ≈ son intégrale : l'oscillation en forme fermée.
                readonly property real oscillation: p.ps !== 0 ? p.sway * (Math.cos(p.phase0) - Math.cos(phase)) / p.ps : 0
                readonly property real xBrut: p.x0 + p.vx * n + oscillation
                                              + (tour !== 0 ? racine._hasard(index, tour) * racine.width : 0)
                readonly property real opaciteCourante: Math.max(0.05, Math.min(0.55,
                    p.base + Math.sin(n * racine.secondesParPas * p.flicker + phase) * p.variation))
                x: -20 + racine._mod(xBrut + 20, racine.width + 40)
                y: -20 + racine._mod(yBrut + 20, hauteurCycle)

                Image {
                    visible: part.p.glow > 0
                    source: visible ? "image://accio/halo/" + part.p.rgb : ""
                    width: part.p.glow * 2; height: width
                    x: -width / 2; y: -height / 2
                    opacity: Math.max(part.opaciteCourante * 0.30, 3 / 255)
                    smooth: true
                }
                Rectangle {
                    visible: part.p.forme === "point"
                    width: part.p.size * 2; height: width; radius: width / 2
                    x: -part.p.size; y: -part.p.size
                    color: Qt.rgba(part.p.r, part.p.g, part.p.b, 1)
                    opacity: part.opaciteCourante
                    antialiasing: true
                }
                Image {
                    visible: part.p.forme !== "point"
                    source: visible ? "image://accio/forme/" + part.p.forme + "/" + part.p.rgb + "/" + part.p.size.toFixed(2) : ""
                    width: part.p.size * 2.4; height: width
                    x: -width / 2; y: -height / 2
                    rotation: part.p.rot0 + part.p.rs * part.n
                    opacity: part.opaciteCourante
                    smooth: true
                }
            }
        }
    }
}

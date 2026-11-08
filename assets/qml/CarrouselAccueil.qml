import QtQuick

// Le double des vignettes du carrousel, dessiné par la carte graphique
// (`src/ui/carrousel_gpu.py`), dans la même scène que les étoiles (une seule
// `QQuickWidget`). Les vrais `CarouselItem` restent la source de vérité (clics,
// survol, géométrie) et ne se peignent plus : à chaque sélection, ils prennent
// d'un coup leur taille finale, et CE sont ces images qui y vont en 400 ms.
// L'ordre des couches est celui de `CarouselItem.paintEvent`, qui en est le
// modèle ; chaque couche à opacité propre (pas d'opacité de groupe).
EtoilesCarrousel {
    id: racine

    property var etats: []             // un objet par vignette, voir `CarouselItem.etat_jumeau`
    property bool animer: false        // faux : la géométrie suit sans animation (taille de la fenêtre)
    property real dpr: 1               // l'échelle de l'écran, pour poser les images sur des pixels entiers

    readonly property int duree: 400   // la durée des animations de `CarouselItem`

    Repeater {
        model: racine.etats.length

        Item {
            id: v
            required property int index
            readonly property var e: racine.etats[index] || ({})

            // Le rectangle du widget : le QPainter ne sort pas de ses bords.
            visible: v.e.visible === true
            clip: true
            x: px
            y: py
            width: cw + 10
            height: ch + refH + 16

            property real px: v.e.x || 0
            property real py: v.e.y || 0
            property real cw: v.e.cw || 0
            property real ch: v.e.ch || 0
            property real refH: v.e.refH || 0
            property real opaciteBase: v.e.opacite === undefined ? 1 : v.e.opacite
            Behavior on px { enabled: racine.animer; NumberAnimation { duration: racine.duree; easing.type: Easing.InOutQuad } }
            Behavior on py { enabled: racine.animer; NumberAnimation { duration: racine.duree; easing.type: Easing.InOutQuad } }
            Behavior on cw { enabled: racine.animer; NumberAnimation { duration: racine.duree; easing.type: Easing.InOutQuad } }
            Behavior on ch { enabled: racine.animer; NumberAnimation { duration: racine.duree; easing.type: Easing.InOutQuad } }
            Behavior on refH { enabled: racine.animer; NumberAnimation { duration: racine.duree; easing.type: Easing.InOutQuad } }
            Behavior on opaciteBase { enabled: racine.animer; NumberAnimation { duration: racine.duree; easing.type: Easing.InOutQuad } }

            // Le survol éclaircit sans animation, comme `CarouselItem._geometrie`.
            readonly property real opacite: (v.e.survol && !v.e.choisi)
                                            ? Math.min(opaciteBase + 0.2, 1) : opaciteBase
            readonly property real refY: 5 + ch + 4
            // Le calque des pastilles se pose sur des pixels entiers de l'écran : à
            // 125 ou 150 %, à cheval, son texte se lissait (le QPainter le pose net).
            readonly property real mx: Math.round((px + 5) * racine.dpr) / racine.dpr - px
            readonly property real my: Math.round((py + 5) * racine.dpr) / racine.dpr - py
            readonly property real mw: Math.round(cw * racine.dpr) / racine.dpr
            readonly property real mh: Math.round(ch * racine.dpr) / racine.dpr

            // ── _peindre_ombre_portee (opacité 0,4) ──
            Repeater {
                model: v.e.choisi ? 4 : 0
                Rectangle {
                    required property int index
                    readonly property real spread: (index + 1) * 3
                    x: 5 - spread
                    y: 5 - spread + 4
                    width: v.cw + spread * 2
                    height: v.ch + spread * 2
                    radius: 6 + spread
                    antialiasing: true
                    color: Qt.rgba(0, 0, 0, Math.max(60 - index * 12, 5) / 255)
                    opacity: 0.4
                }
            }

            // ── _peindre_jaquette (jaquette aux coins arrondis, ou fond de repli) ──
            Image {
                x: 5; y: 5; width: v.cw; height: v.ch
                source: v.e.image || ""
                smooth: true
                opacity: v.opacite
            }
            Image {
                x: 5; y: 5; width: v.cw; height: v.ch
                source: v.e.chiffre || ""
                visible: source != ""
                smooth: true
            }

            // ── _peindre_halo_selection ──
            Repeater {
                model: v.e.choisi ? 3 : 0
                Rectangle {
                    required property int index
                    readonly property real off: (index + 1) * 3
                    x: 5 - off; y: 5 - off
                    width: v.cw + off * 2
                    height: v.ch + off * 2
                    radius: 6 + off
                    antialiasing: true
                    color: Qt.rgba(racine.accent.r, racine.accent.g, racine.accent.b, (25 - index * 7) / 255)
                }
            }
            Rectangle {
                // Le pinceau de 2 px à cheval sur le contour du QPainter (x+1, w-2).
                visible: v.e.choisi === true
                x: 5; y: 5; width: v.cw; height: v.ch
                radius: 7
                antialiasing: true
                color: "transparent"
                border.width: 2
                border.color: Qt.rgba(racine.accent.r, racine.accent.g, racine.accent.b, 1)
            }

            // ── _peindre_reflet ──
            Item {
                visible: v.e.jaquette === true
                x: 5; y: v.refY; width: v.cw; height: v.refH
                clip: true
                Image {
                    width: v.cw; height: v.ch
                    source: v.e.image || ""
                    mirrorVertically: true
                    smooth: true
                    opacity: v.opacite * 0.06
                }
            }
            Rectangle {
                visible: v.e.jaquette === true
                x: 5; y: v.refY; width: v.cw; height: v.refH
                gradient: Gradient {
                    GradientStop { position: 0; color: Qt.rgba(racine.fond.r, racine.fond.g, racine.fond.b, 80 / 255) }
                    GradientStop { position: 1; color: Qt.rgba(racine.fond.r, racine.fond.g, racine.fond.b, 1) }
                }
            }

            // ── _peindre_voile_absent ──
            Image {
                visible: v.e.absent === true && source != ""
                x: 5; y: 5; width: v.cw; height: v.ch
                source: v.e.gris || ""
                smooth: true
                opacity: v.opacite * 0.7
            }
            Rectangle {
                visible: v.e.absent === true
                x: 5; y: 5; width: v.cw; height: v.ch
                radius: 6
                antialiasing: true
                color: Qt.rgba(racine.fond.r, racine.fond.g, racine.fond.b, 70 / 255)
            }

            // ── Badges, voile « bientôt », filet de reprise : une image, peinte par
            // les gestes de `CarouselItem` (`image_marques`) ──
            Image {
                x: v.mx; y: v.my; width: v.mw; height: v.mh
                source: v.e.marques || ""
                visible: source != ""
                smooth: true
            }
        }
    }
}

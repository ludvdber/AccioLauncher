import QtQuick

// Le fond du carrousel, dessiné par la carte graphique (`src/ui/fond_gpu.py`,
// `EtoilesGPU`) : mêmes étoiles que `Carousel.paintEvent`. Repeintes par le
// processeur, ces points de 1 à 2 px recomposaient toute la fenêtre 15 fois par
// seconde (mesuré le 2026-11-01 : 6 points d'un cœur sur 11 au repos). Ici,
// Python n'avance que `phase`.
// Le dégradé de `paintEvent` part de la couleur du fond du thème et se pose sur
// cette même couleur : la bande est unie, un seul rectangle suffit.
Item {
    id: racine

    property color fond: "#060611"
    property color accent: "#d6a72c"
    property real phase: 0
    property var etoiles: []           // [x, y, taille, alpha max, or, phase]

    Rectangle { anchors.fill: parent; color: racine.fond }

    Repeater {
        model: racine.etoiles
        Rectangle {
            required property var modelData
            readonly property var e: modelData
            x: e[0] * racine.width - e[2] / 2
            y: e[1] * racine.height - e[2] / 2
            width: e[2]; height: e[2]; radius: e[2] / 2
            antialiasing: true
            color: e[4] ? Qt.rgba(racine.accent.r, racine.accent.g, racine.accent.b, 1)
                        : Qt.rgba(220 / 255, 220 / 255, 240 / 255, 1)
            // Même scintillement que `paintEvent` : de 0,4 à 1 fois l'alpha maximal.
            opacity: e[3] / 255 * (0.4 + 0.6 * (Math.sin(racine.phase + e[5]) * 0.5 + 0.5))
        }
    }
}

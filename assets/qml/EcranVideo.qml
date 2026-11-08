import QtQuick
import QtMultimedia

// Une cinématique des Collections, dessinée par la carte graphique
// (`src/ui/ecran_video_gpu.py`) : l'image dans son format, sur du noir.
Item {
    id: racine

    property real coin: 0              // l'arrondi de l'écran de la page ; 0 en plein écran
    property color fond: "#070712"     // ce qu'on voit dans les coins, derrière l'arrondi

    Rectangle { anchors.fill: parent; color: "#000000" }

    VideoOutput {
        objectName: "sortieVideo"
        anchors.fill: parent
        fillMode: VideoOutput.PreserveAspectFit
    }

    // Les coins : un cadre de la couleur de la page, dont l'intérieur a l'arrondi
    // voulu. Une scène Qt Quick est opaque : sans lui, les coins restaient carrés.
    Rectangle {
        readonly property real largeur: 8
        visible: racine.coin > 0
        anchors.fill: parent
        anchors.margins: -largeur
        radius: racine.coin + largeur
        color: "transparent"
        border.color: racine.fond
        border.width: largeur
        antialiasing: true
    }
}

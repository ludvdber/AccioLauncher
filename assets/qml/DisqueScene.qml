import QtQuick

// Le disque qui tourne, dessiné par la carte graphique (`src/ui/disque.py`).
// Python ne pousse que l'angle, au rythme du `Ticker` (partagé avec le fond et
// les particules : leurs images partent dans la même composition de la fenêtre).
Item {
    id: racine

    property color fond: "#060611"
    property real angle: 0
    property string disque: ""
    property string ombre: ""          // sous le disque (platine)
    property string lumiere: ""        // au-dessus du disque (platine)

    Rectangle { anchors.fill: parent; color: racine.fond }

    Image {
        anchors.fill: parent
        source: racine.ombre
        visible: racine.ombre !== ""
        smooth: true
    }

    Image {
        anchors.fill: parent
        source: racine.disque
        smooth: true
        antialiasing: true
        transformOrigin: Item.Center
        rotation: racine.angle
    }

    Image {
        anchors.fill: parent
        source: racine.lumiere
        visible: racine.lumiere !== ""
        smooth: true
    }
}

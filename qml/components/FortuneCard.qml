// Fortune Card (draft: personal/Glueckskeks-Labor.html): the logo card with a dog-ear lies mirrored, wobbles now
// and then with a shimmer. Click: it turns the right way round (fold front right, darkened) and the slip
// slides out over the card – the saying in bold italics, below it „Bent°Corner · Fortune Card“. After the first
// click nothing wobbles any more. Second click (card or slip): first the slip rolls in, then the card turns back and
// fades. Sayings for now: only „Pack it, rip it, hit it!“ (the collecting idea is in the backlog).
import QtQuick
import QtQuick.Shapes

Item {
    id: root
    property string quote: "Pack it, rip it, hit it!"
    property string label: "Bent°Corner · Fortune Card"
    property bool clicked: false
    property string phase: "closed"   // closed · open · gone
    implicitWidth: 380; implicitHeight: 150

    readonly property real cw: 64
    readonly property real ch: 90
    // card as a polygon (corner top right or – mirrored – top left cut off)
    component CardShape: Shape {
        id: cs
        property bool front: true
        property real shine: -1           // shimmer: position of the bright stripe (−1 … 2), invisible outside
        readonly property real r: width * 0.045   // corner radius like real cards
        width: root.cw; height: root.ch
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: "transparent"
            fillGradient: LinearGradient { x1: 0; y1: 0; x2: cs.width; y2: cs.height
                GradientStop { position: 0; color: cs.front ? "#f6f6f6" : "#e9e9ea" }
                GradientStop { position: 1; color: cs.front ? "#d2d2d5" : "#c4c4c8" } }
            // rounded corners (r) like real cards – only the dog-ear stays a straight edge
            startX: cs.front ? cs.r : cs.width * 0.3; startY: 0
            PathLine { x: cs.front ? cs.width * 0.7 : cs.width - cs.r; y: 0 }
            PathQuad { x: cs.width; y: cs.front ? cs.height * 0.21 : cs.r
                       controlX: cs.front ? cs.width * 0.85 : cs.width; controlY: cs.front ? cs.height * 0.105 : 0 }
            PathLine { x: cs.width; y: cs.height - cs.r }
            PathQuad { x: cs.width - cs.r; y: cs.height; controlX: cs.width; controlY: cs.height }
            PathLine { x: cs.r; y: cs.height }
            PathQuad { x: 0; y: cs.height - cs.r; controlX: 0; controlY: cs.height }
            PathLine { x: 0; y: cs.front ? cs.r : cs.height * 0.21 }
            PathQuad { x: cs.front ? cs.r : cs.width * 0.3; y: 0
                       controlX: cs.front ? 0 : cs.width * 0.15; controlY: cs.front ? 0 : cs.height * 0.105 }
        }
        ShapePath {   // shimmer: the same surface, a bright stripe runs diagonally across it
            strokeColor: "transparent"
            fillGradient: LinearGradient { x1: 0; y1: 0; x2: cs.width; y2: cs.height * 0.5
                GradientStop { position: Math.max(0, cs.shine - 0.18); color: "#00ffffff" }
                GradientStop { position: Math.max(0, Math.min(1, cs.shine)); color: cs.shine > -0.2 && cs.shine < 1.2 ? "#ccffffff" : "#00ffffff" }
                GradientStop { position: Math.min(1, cs.shine + 0.18); color: "#00ffffff" } }
            // rounded corners (r) like real cards – only the dog-ear stays a straight edge
            startX: cs.front ? cs.r : cs.width * 0.3; startY: 0
            PathLine { x: cs.front ? cs.width * 0.7 : cs.width - cs.r; y: 0 }
            PathQuad { x: cs.width; y: cs.front ? cs.height * 0.21 : cs.r
                       controlX: cs.front ? cs.width * 0.85 : cs.width; controlY: cs.front ? cs.height * 0.105 : 0 }
            PathLine { x: cs.width; y: cs.height - cs.r }
            PathQuad { x: cs.width - cs.r; y: cs.height; controlX: cs.width; controlY: cs.height }
            PathLine { x: cs.r; y: cs.height }
            PathQuad { x: 0; y: cs.height - cs.r; controlX: 0; controlY: cs.height }
            PathLine { x: 0; y: cs.front ? cs.r : cs.height * 0.21 }
            PathQuad { x: cs.front ? cs.r : cs.width * 0.3; y: 0
                       controlX: cs.front ? 0 : cs.width * 0.15; controlY: cs.front ? 0 : cs.height * 0.105 }
        }
        ShapePath {   // front: the folded part, darkened
            strokeColor: "transparent"; fillColor: cs.front ? "#8a8a8e" : "transparent"
            startX: cs.width * 0.7; startY: 0
            PathLine { x: cs.width; y: cs.height * 0.21 }
            PathLine { x: cs.width * 0.7; y: cs.height * 0.21 }
            PathLine { x: cs.width * 0.7; y: 0 }
        }
    }

    Item {
        id: holder
        x: root.width - root.cw - 26; y: (root.height - root.ch) / 2
        width: root.cw; height: root.ch
        opacity: root.phase === "gone" ? 0 : 1
        Behavior on opacity { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
        transform: Rotation { id: wob; origin.x: root.cw / 2; origin.y: root.ch * 0.8; angle: 0 }
        Flipable {
            id: flip
            anchors.fill: parent
            rotation: -7
            property real turn: root.phase === "open" ? 0 : 180
            Behavior on turn { NumberAnimation { duration: 760; easing.type: Easing.OutBack; easing.overshoot: 0.9 } }
            transform: Rotation { origin.x: root.cw / 2; origin.y: root.ch / 2; axis.x: 0; axis.y: 1; axis.z: 0; angle: flip.turn }
            front: CardShape { front: true }
            back: CardShape { id: backShape; front: false }
        }
        HoverHandler { cursorShape: root.phase === "gone" ? Qt.ArrowCursor : Qt.PointingHandCursor }
        TapHandler { enabled: root.phase !== "gone"; onTapped: root.toggle() }
    }
    // slip: lies over the card after turning, rolls out to the left
    Rectangle {
        id: slip
        z: 2
        readonly property real full: Math.max(240, quoteText.implicitWidth + 44)
        anchors.right: holder.right; anchors.rightMargin: -12
        y: holder.y + root.ch * 0.38
        height: 64; radius: 4; clip: true
        property bool out: false
        width: out ? full : 0
        Behavior on width { NumberAnimation { duration: slip.out ? 620 : 520
                                              easing.type: slip.out ? Easing.OutBack : Easing.InCubic } }
        color: "#ededed"
        rotation: -3; transformOrigin: Item.Right
        Text { id: quoteText; anchors.right: parent.right; anchors.rightMargin: 20; y: 12; text: root.quote
               color: "#121214"; font.family: T.font; font.pixelSize: 17; font.bold: true; font.italic: true }
        Text { anchors.right: parent.right; anchors.rightMargin: 20; y: 42; text: root.label
               color: "#8a8a8e"; font.family: T.display; font.pixelSize: 9; font.letterSpacing: 2; font.capitalization: Font.AllUppercase }
        TapHandler { onTapped: root.toggle() }
    }
    Timer {   // first turn the card over, then let the slip slide out
        id: slipLater; interval: 520
        onTriggered: slip.out = true
    }
    Timer { id: goneLater; interval: 520; onTriggered: root.phase = "gone" }

    function toggle() {
        if (phase === "closed") { clicked = true; wobbleAnim.stop(); wob.angle = 0; phase = "open" }
        else if (phase === "open" && slip.out) { slip.out = false; goneLater.start() }
    }
    onPhaseChanged: if (phase === "open") slipLater.start()

    // wobble + shimmer every few seconds – only as long as nobody has clicked yet
    Timer { interval: 3800; repeat: true; running: !root.clicked && root.visible; onTriggered: wobbleAnim.restart() }
    ParallelAnimation {
        id: wobbleAnim
        SequentialAnimation {
            NumberAnimation { target: wob; property: "angle"; to: -9; duration: 135 }
            NumberAnimation { target: wob; property: "angle"; to: 7; duration: 135 }
            NumberAnimation { target: wob; property: "angle"; to: -5; duration: 135 }
            NumberAnimation { target: wob; property: "angle"; to: 3; duration: 135 }
            NumberAnimation { target: wob; property: "angle"; to: 0; duration: 220 }
        }
        NumberAnimation { target: backShape; property: "shine"; from: -0.4; to: 1.6; duration: 1100; easing.type: Easing.OutQuad }
    }
}

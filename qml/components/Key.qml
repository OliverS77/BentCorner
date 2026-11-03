// Key surface – the ONE look of all buttons (key lab „B · OP-XY knapp“): key = housing colour, very short hard
// shadows (light top left, shadow bottom right), a sharp 1 px highlight edge top left and a fine dark
// edge bottom right. Pressed: shadow inwards, highlight and edge gone at once; released: short spring.
// All values here – changing the look = only this file. Built lean (5 parts), there are hundreds of buttons.
import QtQuick
import QtQuick.Effects

Item {
    id: k
    property real radius: 9
    property bool down: false            // pressed (mouse down)
    property bool light: false           // bright key (inverted: e.g. pin/alarm on)
    // --- Values from the lab ---
    // inverted key (light): bright in the dark look, dark in the light look
    readonly property bool bright: light !== T.light
    readonly property color face: light ? (T.light ? "#2a2a2e" : "#d6d6d6") : T.keyFace
    readonly property color lightC: light ? (T.light ? "#3a3a3e" : "#f4f4f4") : T.keyLight
    readonly property color darkC: T.keyDark
    readonly property real dist: 3
    readonly property real blur: 6
    readonly property real glossA: bright ? 0.55 : 0.22     // highlight edge: strength, length (share of the diagonal)
    readonly property real glossL: 0.55
    readonly property real edgeA: bright ? 0.25 : 0.60      // dark edge bottom right
    readonly property real edgeL: 0.40
    readonly property int downMs: 70
    readonly property int upMs: 241
    readonly property real pressScale: 0.19                // 0 … 1 → up to 2 % smaller

    // p: 0 = up, 1 = pressed – down fast, up with spring (like cubic-bezier(.34, 1.7, .5, 1))
    property real p: down ? 1 : 0
    Behavior on p { NumberAnimation { duration: k.down ? k.downMs : k.upMs
                                      easing.type: k.down ? Easing.OutQuad : Easing.OutBack; easing.overshoot: 1.7 } }
    readonly property real up: Math.max(0, 1 - p)           // how far the key sticks out (spring: briefly > 1)
    readonly property real gloss: Math.max(0, 1 - 1.7 * p)  // highlight vanishes faster than the key sinks
    readonly property real pin: Math.min(1, Math.max(0, p)) // inner shadow
    scale: 1 - 0.02 * pressScale * pin
    readonly property real span: (width + height) / Math.max(1, width)   // diagonal → horizontal gradient

    // ---- Outer shadow (light top left, dark bottom right) – GPU only; loaded later in the background,
    // so hundreds of buttons don't hold up startup ----
    Loader {
        anchors.fill: parent
        asynchronous: true
        active: GraphicsInfo.api !== GraphicsInfo.Software
        sourceComponent: Item {
            RectangularShadow {
                anchors.fill: parent
                visible: k.up > 0.01
                offset.x: -k.dist * k.up; offset.y: -k.dist * k.up
                radius: k.radius; blur: k.blur
                color: k.lightC
                opacity: Math.min(1, k.up)
            }
            RectangularShadow {
                anchors.fill: parent
                visible: k.up > 0.01
                offset.x: k.dist * k.up; offset.y: k.dist * k.up
                radius: k.radius; blur: k.blur
                color: k.darkC
                opacity: Math.min(1, k.up)
            }
        }
    }
    // ---- Highlight edge: surface with gradient; of it 1 px stays visible at the top and left ----
    Rectangle {
        anchors.fill: parent
        radius: k.radius
        gradient: Gradient { orientation: Gradient.Horizontal
            GradientStop { position: 0; color: Qt.tint(k.face, Qt.rgba(1, 1, 1, k.glossA * k.gloss)) }
            GradientStop { position: Math.min(1, k.glossL * k.span); color: k.face } }
    }
    // ---- Dark edge: offset by 1 px; of it 1 px stays visible at the bottom and right ----
    Rectangle {
        x: 1; y: 1; width: parent.width - 1; height: parent.height - 1
        radius: Math.max(0, k.radius - 0.5)
        gradient: Gradient { orientation: Gradient.Horizontal
            GradientStop { position: Math.max(0, 1 - k.edgeL * k.span); color: k.face }
            GradientStop { position: 1; color: Qt.tint(k.face, Qt.rgba(0, 0, 0, k.edgeA * k.gloss)) } }
    }
    // ---- Surface: pressed with inner shadow (dark at the top, light at the bottom) ----
    Rectangle {
        id: faceR
        x: 1; y: 1; width: parent.width - 2; height: parent.height - 2
        radius: Math.max(0, k.radius - 1)
        readonly property real band: Math.min(0.45, (k.dist * 0.8 + k.blur * 0.6) / Math.max(1, height))
        gradient: Gradient {
            GradientStop { position: 0; color: Qt.tint(k.face, Qt.rgba(k.darkC.r, k.darkC.g, k.darkC.b, k.pin)) }
            GradientStop { position: Math.max(0.01, faceR.band * k.pin); color: k.face }
            GradientStop { position: Math.min(0.99, 1 - faceR.band * 0.8 * k.pin); color: k.face }
            GradientStop { position: 1; color: Qt.tint(k.face, Qt.rgba(k.lightC.r, k.lightC.g, k.lightC.b, 0.9 * k.pin)) } }
    }
}

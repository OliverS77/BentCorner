// Large card of the detail view (like libview.CardView): flies in from behind (zoom + tilt), then a light
// reflection sweeps once across the card. Hover tilts the card towards the mouse; opposite a highlight (foils:
// rainbow), the shadow grows. Flip = rotation about the vertical axis, other image (language) = crossfade.
import QtQuick
import QtQuick.Effects
import QtQuick.Shapes

Item {
    id: c
    property url source
    property int gen: 0
    property string mode: "in"
    property bool foil: false
    // Pokémon (provisional): "holo" = shine only in the art window, "reverse" = everywhere but the art, "" = whole card
    property string holo: ""
    readonly property rect artBox: Qt.rect(0.085, 0.105, 0.83, 0.375)   // art window of modern Pokémon cards (relative)
    property string text: ""
    property string loadingName: ""
    property bool missing: false      // no image online: the crossed-out card (NoImage)
    property bool held: false        // view still gliding: still and fully visible, the reflection comes afterwards
    property bool sweepLater: false
    property real glow: 0            // short light pulse on landing
    onHeldChanged: if (!held && sweepLater) { sweepLater = false; sweepAnim.restart() }
    readonly property real margin: 44
    readonly property real cw: width - margin
    readonly property real ch: cw * 88 / 63
    implicitHeight: ch + margin
    readonly property bool fx: GraphicsInfo.api !== GraphicsInfo.Software

    // images: current and previous (for flip/crossfade)
    property url cur
    property url prev
    // Two image slots alternating: the image loads asynchronously – the new one loads in the free slot, the old (ready)
    // one stays until then (silent replace) or serves as the „previous“ image when flipping/crossfading. Otherwise the
    // card would be blank for a frame e.g. when the view gets wider/narrower and Python delivers the card again.
    property int act: 0
    property url srcA
    property url srcB
    readonly property var actImg: act === 0 ? imgA : imgB
    readonly property var otherImg: act === 0 ? imgB : imgA
    readonly property bool ready: cur.toString() === "" || (actImg.source.toString() === cur.toString() && actImg.status === Image.Ready)
    function load(url, quiet) {
        if (actImg.source.toString() === url.toString()) return
        if (act === 0) srcB = url; else srcA = url
        if (!quiet) act = 1 - act               // new card: switch right away (it flies in anyway)
        else if (otherImg.status === Image.Ready) act = 1 - act   // already ready (e.g. from the cache)
    }
    function slotReady(slot) {   // silent replace: switch as soon as the new image is ready
        var img = slot === 0 ? imgA : imgB
        if (slot !== act && img.source.toString() === cur.toString() && img.status === Image.Ready) act = slot
    }
    property real u: 1          // arrival progress
    property real sweep: -1     // light reflection 0..1 (−1 = off)
    property bool showPrev: false
    // gen and source arrive in any order – decide only when both are there: new gen = new
    // card (fly in), otherwise the same image in better resolution = silent replace
    property int seenGen: 0
    property string pic: ""          // "gen|url" from Python – both always arrive together this way
    function parsePic() {
        var i = pic.indexOf("|")
        if (i < 0) return false
        gen = parseInt(pic.slice(0, i)); source = pic.slice(i + 1)
        return true
    }
    onPicChanged: if (parsePic()) take()
    function take() {
        if (gen !== seenGen) {
            seenGen = gen
            prev = cur; cur = source
            load(cur, false)
            arrive.stop(); sweepAnim.stop()
            if (held && mode === "in") { u = 1; sweepLater = true; return }
            u = 0
            arrive.start()
        } else if (source.toString() !== cur.toString()) {
            cur = source
            load(cur, true)
        }
    }
    Component.onCompleted: {   // newly built (e.g. first card opened): fly in with the image already present
        parsePic()
        seenGen = gen; cur = source; srcA = cur; act = 0
        if (cur.toString() !== "" && shell.animate) {
            if (held) sweepLater = true
            else { u = 0; arrive.start() }
        }
    }

    SequentialAnimation {
        id: arrive
        ParallelAnimation {
            NumberAnimation { target: c; property: "u"; from: 0; to: 1
                              duration: (c.mode === "swap" ? 350 : c.mode === "fade" ? 300 : 550) * Math.max(0.01, shell.speed)
                              easing.type: c.mode === "flip" ? Easing.InOutCubic : Easing.OutCubic }
            SequentialAnimation {
                PauseAnimation { duration: (c.mode === "flip" ? 550 : c.mode === "in" ? 300 : 120) * Math.max(0.01, shell.speed) }
                ScriptAction { script: if (c.mode !== "swap") sweepAnim.restart() }
            }
            SequentialAnimation {   // landing: short light pulse around the card
                PauseAnimation { duration: (c.mode === "in" ? 200 : 0) * Math.max(0.01, shell.speed) }
                NumberAnimation { target: c; property: "glow"; from: 0; to: c.mode === "in" ? 0.6 : 0; duration: 350 * Math.max(0.01, shell.speed) }
                NumberAnimation { target: c; property: "glow"; to: 0; duration: 350 * Math.max(0.01, shell.speed) }
            }
        }
    }
    NumberAnimation { id: sweepAnim; target: c; property: "sweep"; from: 0; to: 1; duration: 950
                      easing.type: Easing.InOutSine; onFinished: c.sweep = -1 }

    // hover: tilt towards the mouse, light opposite
    property real nx: 0
    property real ny: 0
    property real lift: hover.hovered ? 1 : 0
    Behavior on lift { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
    property real tiltY: hover.hovered ? -nx * 10 : 0
    property real tiltX: hover.hovered ? ny * 8 : 0
    Behavior on tiltY { SmoothedAnimation { velocity: 120 } }
    Behavior on tiltX { SmoothedAnimation { velocity: 100 } }
    HoverHandler {
        id: hover
        onPointChanged: {
            c.nx = Math.max(-1, Math.min(1, (point.position.x - c.width / 2) / (c.width / 2)))
            c.ny = Math.max(-1, Math.min(1, (point.position.y - c.height / 2) / (c.height / 2)))
        }
    }

    // angle/size depending on the kind of arrival
    readonly property real arriveRotY: mode === "flip" ? (u < 0.5 ? u * 180 : (u - 1) * 180)
                                       : mode === "in" ? -16 * (1 - u) : 0
    readonly property real arriveRotX: mode === "in" ? 6 * (1 - u) : 0
    readonly property real arriveScale: mode === "in" ? 0.84 + 0.16 * u
                                        : mode === "flip" ? 1 - 0.07 * Math.sin(u * Math.PI)
                                        : mode === "swap" ? 0.94 + 0.06 * u : 1
    readonly property real arriveOpacity: mode === "in" || mode === "fade" || mode === "swap" ? u : 1
    readonly property bool flipBack: mode === "flip" && u < 0.5

    // glow on landing or slightly on lifting (staggered surfaces behind the card, tilted along)
    Item {
        x: c.margin / 2; y: c.margin / 2; width: c.cw; height: c.ch
        readonly property real g: Math.max(c.glow, 0.25 * c.lift) * c.arriveOpacity
        visible: g > 0.01 && c.cur.toString() !== ""
        transform: [
            Rotation { origin.x: c.cw / 2; origin.y: c.ch / 2; axis.x: 0; axis.y: 1; axis.z: 0; angle: c.arriveRotY + c.tiltY },
            Rotation { origin.x: c.cw / 2; origin.y: c.ch / 2; axis.x: 1; axis.y: 0; axis.z: 0; angle: c.arriveRotX + c.tiltX },
            Scale { origin.x: c.cw / 2; origin.y: c.ch / 2; xScale: c.arriveScale * (1 - 0.015 * c.lift); yScale: xScale }
        ]
        Repeater {
            model: [[10, 0.07], [6, 0.1], [2.5, 0.3]]
            Rectangle {
                required property var modelData
                x: -modelData[0]; y: -modelData[0]
                width: parent.width + 2 * modelData[0]; height: parent.height + 2 * modelData[0]
                radius: c.cw * 0.053 + modelData[0]
                color: Qt.rgba(1, 1, 1, Math.min(1, modelData[1] * parent.g))
            }
        }
    }
    // shadow (grows with lifting, falls away from the mouse)
    Repeater {
        model: [[12, 0.06], [6, 0.10], [1, 0.16]]
        Rectangle {
            required property var modelData
            x: c.margin / 2 - modelData[0] + (-c.nx) * 8 * c.lift
            y: c.margin / 2 - modelData[0] + 3 + 4 * c.lift
            width: c.cw + 2 * modelData[0]; height: c.ch + 2 * modelData[0]
            radius: c.cw * 0.053 + modelData[0]
            color: Qt.rgba(0, 0, 0, 0.59 * modelData[1] * Math.max(c.lift, 0.35) * c.arriveOpacity)
        }
    }

    // card surface (flat), from which the rounded, tilted card is made
    Item {
        id: face
        x: c.margin / 2; y: c.margin / 2
        width: c.cw; height: c.ch
        visible: !c.fx && c.cur.toString() !== ""
        opacity: c.fx ? 1 : c.arriveOpacity
        layer.enabled: c.fx
        layer.smooth: true
        transform: c.fx ? [] : tilt

        // current slot: card; other slot: previous image (flip: first half; crossfade: fades over it)
        readonly property bool prevShown: c.flipBack || (c.mode === "swap" && c.u < 1)
        Image {
            id: imgA
            anchors.fill: parent
            source: c.srcA
            z: c.act === 0 ? 0 : 1
            opacity: c.act === 0 ? (c.flipBack ? 0 : 1) : (face.prevShown ? (c.mode === "swap" ? 1 - c.u : 1) : 0)
            asynchronous: false; smooth: true; mipmap: true; cache: false
            onStatusChanged: c.slotReady(0)
        }
        Image {
            id: imgB
            anchors.fill: parent
            source: c.srcB
            z: c.act === 1 ? 0 : 1
            opacity: c.act === 1 ? (c.flipBack ? 0 : 1) : (face.prevShown ? (c.mode === "swap" ? 1 - c.u : 1) : 0)
            asynchronous: false; smooth: true; mipmap: true; cache: false
            onStatusChanged: c.slotReady(1)
        }
    }
    Item {
        id: mask
        width: face.width; height: face.height
        layer.enabled: true
        visible: false
        Rectangle { anchors.fill: parent; radius: face.width * 0.053; color: "black" }
    }
    MultiEffect {   // rounded corners, then tilt
        x: face.x; y: face.y; width: face.width; height: face.height
        source: face
        visible: c.fx && c.cur.toString() !== ""
        maskEnabled: true
        maskSource: mask
        opacity: c.arriveOpacity
        transform: tilt
    }
    // glow at the mouse: own layer above the card, tilts along (in the hidden effect layer the shape would not
    // be drawn)
    Item {
        id: glareLayer
        x: c.margin / 2; y: c.margin / 2; width: c.cw; height: c.ch
        visible: c.lift > 0.01 && c.cur.toString() !== ""
        clip: true
        opacity: c.arriveOpacity
        transform: [
            Rotation { origin.x: c.cw / 2; origin.y: c.ch / 2; axis.x: 0; axis.y: 1; axis.z: 0; angle: c.arriveRotY + c.tiltY },
            Rotation { origin.x: c.cw / 2; origin.y: c.ch / 2; axis.x: 1; axis.y: 0; axis.z: 0; angle: c.arriveRotX + c.tiltX },
            Scale { origin.x: c.cw / 2; origin.y: c.ch / 2; xScale: c.arriveScale * (1 - 0.015 * c.lift); yScale: xScale }
        ]
        // areas where the glow is visible (relative to the card): whole card, only the art (holo) or
        // four strips around the art (reverse holo). Each area clips the same shine surface.
            Repeater {
                model: {
                    var a = c.artBox
                    if (c.holo === "holo") return [a]
                    if (c.holo === "reverse") return [Qt.rect(0, 0, 1, a.y), Qt.rect(0, a.y + a.height, 1, 1 - a.y - a.height),
                                                      Qt.rect(0, a.y, a.x, a.height),
                                                      Qt.rect(a.x + a.width, a.y, 1 - a.x - a.width, a.height)]
                    return [Qt.rect(0, 0, 1, 1)]
                }
                delegate: Item {
                    id: region
                    required property rect modelData
                    x: modelData.x * glareLayer.width; y: modelData.y * glareLayer.height
                    width: modelData.width * glareLayer.width; height: modelData.height * glareLayer.height
                    clip: true
                    Item {
                        x: -region.x; y: -region.y; width: glareLayer.width; height: glareLayer.height
                        Shape {   // glow exactly at the mouse: normal card white, foil as rainbow (only there, not the whole card)
                            id: glare
                            readonly property real rad: glareLayer.width * (c.foil ? 0.34 : 0.3)
                            width: rad * 2; height: rad * 2
                            x: (c.nx + 1) / 2 * glareLayer.width - rad
                            y: (c.ny + 1) / 2 * glareLayer.height - rad
                            opacity: c.lift
                            visible: c.lift > 0.01
                            ShapePath {
                                strokeWidth: -1
                                fillGradient: RadialGradient {
                                    centerX: glare.rad; centerY: glare.rad; centerRadius: glare.rad
                                    focalX: glare.rad; focalY: glare.rad
                                    GradientStop { position: 0; color: Qt.rgba(1, 1, 1, c.foil ? 0.42 : 0.4) }
                                    GradientStop { position: c.foil ? 0.18 : 0.35; color: c.foil ? Qt.rgba(1, 0.36, 0.84, 0.30) : Qt.rgba(0.94, 0.97, 1, 0.16) }
                                    GradientStop { position: c.foil ? 0.36 : 0.7; color: c.foil ? Qt.rgba(0.38, 0.95, 1, 0.26) : Qt.rgba(1, 1, 1, 0.04) }
                                    GradientStop { position: c.foil ? 0.54 : 0.85; color: c.foil ? Qt.rgba(1, 0.9, 0.43, 0.22) : Qt.rgba(1, 1, 1, 0.01) }
                                    GradientStop { position: c.foil ? 0.72 : 0.92; color: c.foil ? Qt.rgba(0.27, 0.82, 0.48, 0.15) : Qt.rgba(1, 1, 1, 0) }
                                    GradientStop { position: 1; color: Qt.rgba(1, 1, 1, 0) }
                                }
                                startX: 0; startY: 0
                                PathLine { x: glare.width; y: 0 }
                                PathLine { x: glare.width; y: glare.height }
                                PathLine { x: 0; y: glare.height }
                                PathLine { x: 0; y: 0 }
                            }
                        }
                    }
                }
            }
    }
    // light reflection after popping up: simple surface on top, a bright stripe moves once from top left
    // to bottom right across the card
    Item {
        id: sweepLayer
        x: c.margin / 2; y: c.margin / 2; width: c.cw; height: c.ch
        visible: c.sweep >= 0 && c.cur.toString() !== ""
        clip: true
        opacity: c.arriveOpacity
        readonly property real diag: Math.sqrt(width * width + height * height)
        Rectangle {
            width: sweepLayer.diag * 0.32; height: sweepLayer.diag * 1.6
            rotation: 45
            x: sweepLayer.width * (-0.35 + 1.7 * c.sweep) - width / 2
            y: sweepLayer.height * (-0.35 + 1.7 * c.sweep) - height / 2
            gradient: Gradient { orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0) }
                GradientStop { position: 0.35; color: Qt.rgba(1, 1, 1, c.foil ? 0.18 : 0.14) }
                GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, c.foil ? 0.5 : 0.42) }
                GradientStop { position: 0.65; color: Qt.rgba(1, 1, 1, c.foil ? 0.18 : 0.14) }
                GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0) } }
        }
    }
    property list<QtObject> tilt: [
        Rotation { origin.x: c.cw / 2; origin.y: c.ch / 2; axis.x: 0; axis.y: 1; axis.z: 0; angle: c.arriveRotY + c.tiltY },
        Rotation { origin.x: c.cw / 2; origin.y: c.ch / 2; axis.x: 1; axis.y: 0; axis.z: 0; angle: c.arriveRotX + c.tiltX },
        Scale { origin.x: c.cw / 2; origin.y: c.ch / 2; xScale: c.arriveScale * (1 - 0.015 * c.lift); yScale: xScale }
    ]

    // still loading: card outline (with name) and the light stripe – holds the space so nothing below jumps
    Rectangle {
        x: c.margin / 2; y: c.margin / 2
        width: c.cw; height: c.ch
        visible: c.cur.toString() === "" && c.text === "" && !c.missing
        radius: c.cw * 0.053
        color: T.surface2
        border.width: 1.5; border.color: T.line
        Text { anchors.centerIn: parent; width: parent.width - 30; text: c.loadingName; color: T.dim
               font.family: T.font; font.pixelSize: 15; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter }
        Shimmer { anchors.fill: parent; anchors.margins: 2; running: parent.visible }
    }
    NoImage {   // no image at the source: the crossed-out card (different from loading on purpose)
        x: c.margin / 2; y: c.margin / 2
        width: c.cw; height: c.ch; radius: c.cw * 0.053
        visible: c.cur.toString() === "" && c.text === "" && c.missing
    }
    Text {   // hint (e.g. „Loading FR version …“)
        anchors.fill: parent; anchors.margins: 40
        visible: c.text !== ""
        text: c.text
        color: T.muted; font.family: T.font; font.pixelSize: 15
        wrapMode: Text.Wrap
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
    }
}

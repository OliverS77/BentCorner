// Card in the grid (like libview.CardDelegate): image with rounded corners, chips on the right of the image, below
// name + price and the sets. Hover lifts the card (shadow + glow), selected = border, missing = dimmed.
// While the image is still loading: card outline with name and calm light waves.
import QtQuick

Item {
    id: t
    property string name
    property string price
    property string setLine
    property var chips: []
    property string cond: ""   // condition (EX, LP, PSA 10 …) – own outlined box bottom left in the image
    property url img
    property bool pending: false     // slow image server: the image is still queued – light waves, no request yet
    property bool dim: false
    property bool selected: false
    property string nameColor: ""
    property real appearDelay: 0     // staggered fade-in after a new search (s)
    property bool appearing: false
    property var decks: []           // decks the card is in: [{deck, n, built}] (badge top left)
    property bool draggable: false   // card can be dragged out (Trade: into a list)
    property bool checkable: false   // checkmark bottom right (trade offer)
    property bool checked: false
    property int tileIndex: -1       // row in the grid (for gliding, see LibraryView.syncLayout)
    // several cards chosen (Library, review .106): selection = brightness – chosen ones bright with a frame a little away
    // from the card and lifted a touch, the others dimmed (hover: almost normal). No ticks.
    property bool selMode: false
    property bool choosing: false   // "Select" is on: every tap chooses (no double click)
    property bool picked: false
    property color pickColor: T.text
    property int clickMods: 0        // keyboard modifiers of the last click (Ctrl/Shift = choose instead of open)
    readonly property real selA: !selMode || picked ? 1 : (hover.hovered ? 0.85 : 0.38)
    property real selAA: selA
    Behavior on selAA { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
    signal clicked()
    signal doubleClicked()
    signal checkToggled()
    signal dragMoved(real sx, real sy)
    signal dragEnded(real sx, real sy)

    readonly property real cw: width - 16
    readonly property real ch: cw * 88 / 63
    readonly property int npx: Math.max(10, Math.min(16, Math.round(cw / 13)))
    readonly property real radius: Math.max(5, cw * 0.053)
    readonly property bool fx: GraphicsInfo.api !== GraphicsInfo.Software

    property bool calm: false        // without hover lift/frame (e.g. Trade columns with checkmarks)
    property real hv: hover.hovered && !calm ? 1 : 0
    Behavior on hv { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

    // fade in: glide up softly + fade in (no scaling)
    property real a: 1
    onAppearingChanged: if (appearing) { a = 0; appearAnim.restart() }
    SequentialAnimation {
        id: appearAnim
        PauseAnimation { duration: Math.round(t.appearDelay * 1000) }
        NumberAnimation { target: t; property: "a"; from: 0; to: 1; duration: 380; easing.type: Easing.OutCubic }
    }

    // glide (detail open/closed, other card count): from the old place to the new one, growing/shrinking to fit;
    // cards changing row fly over the others and dip slightly on the way (-6 %)
    property real gx: 0
    property real gy: 0
    property real gs: 1
    property real gk: 1
    property bool gLift: false
    property bool gFade: false
    // focus (LibraryView): fade image and text separately, scale around the centre, move (flight)
    property real imgA: 1
    property real txtA: 1
    property real fs: 1
    property real fdx: 0
    property real fdy: 0
    property bool fTop: false        // focus: the flying card lies on top
    property real gz: 0
    z: fTop ? 5 : gz
    function glideFrom(dx, dy, s, ms, lift, fade) {
        gx = dx; gy = dy; gs = s; gLift = lift; gFade = fade
        gz = lift ? 2 : 1
        gk = 0
        glideAnim.duration = Math.max(1, ms)
        glideAnim.restart()
    }
    NumberAnimation {
        id: glideAnim
        target: t; property: "gk"; from: 0; to: 1
        easing.type: Easing.OutBack; easing.overshoot: 0.9
        onRunningChanged: if (!running) { t.gz = 0; t.gFade = false; t.gLift = false }
    }
    readonly property real dip: gLift ? 1 - 0.06 * Math.sin(Math.PI * Math.max(0, Math.min(1, gk))) : 1
    readonly property real gsc: gs + (1 - gs) * gk
    opacity: gFade ? Math.min(1, Math.max(0, gk) * 1.6) : 1
    transform: [
        Scale { origin.x: t.width / 2; origin.y: t.height / 2; xScale: t.dip; yScale: t.dip },
        Scale { xScale: t.gsc; yScale: t.gsc },
        Translate { x: t.gx * (1 - t.gk); y: t.gy * (1 - t.gk) },
        Scale { origin.x: t.width / 2; origin.y: t.height / 2; xScale: t.fs; yScale: t.fs },
        Translate { x: t.fdx; y: t.fdy }
    ]

    Item {
        id: card
        x: 8; y: 8 + Math.round((1 - t.a) * 18 - 6 * t.hv)
        width: t.cw; height: t.ch
        opacity: t.a * t.imgA * t.selAA
        scale: t.picked ? 1.02 : 1
        Behavior on scale { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
        Rectangle {   // chosen: a frame with a small gap, so it shows on white card borders too
            visible: t.picked
            anchors.fill: parent; anchors.margins: -5
            radius: t.radius + 5
            color: "transparent"
            border.width: 2; border.color: t.pickColor
        }

        // shadow + glow (hover/selection). The shadow lies under the card: only under a full, opaque image – a dimmed
        // card or the crossed-out one (no image) would darken on hover (Oliver: nothing darkens on hover)
        Rectangle {
            visible: (t.hv > 0.01 || t.selected) && card.imgReady && !t.dim
            opacity: Math.max(t.hv, t.selected ? 0.75 : 0)
            anchors.fill: parent; anchors.margins: -3; anchors.topMargin: 3; anchors.bottomMargin: -13
            radius: t.radius + 3
            color: Qt.rgba(0, 0, 0, 0.35)
        }
        Rectangle {
            visible: t.hv > 0.01 || t.selected
            opacity: Math.max(t.hv, t.selected ? 0.75 : 0) * 0.55
            anchors.fill: parent; anchors.margins: -4
            radius: t.radius + 4
            color: "transparent"
            border.width: 4
            border.color: Qt.rgba(1, 1, 1, 0.16)
        }

        // placeholder while the image loads (name + light stripe) – if there is none (source has no image), the
        // crossed-out card (NoImage) shows instead; name and sets stand under the tile already
        readonly property bool noImg: !t.pending && (t.img.toString() === "" || (card.wantS ? imgS.status === Image.Error : true)
                                                    && (card.wantB ? imgB.status === Image.Error : true))
        // placeholder while loading: built only then (every item in the window costs in every frame)
        Loader {
            anchors.fill: parent
            active: !card.imgReady && !card.noImg
            sourceComponent: Rectangle {
                id: ph
                anchors.fill: parent
                radius: t.radius
                color: T.surface2
                border.width: 1.5; border.color: T.line
                clip: true
                Text {
                    anchors.fill: parent; anchors.margins: 10
                    text: t.name
                    color: T.dim; font.family: T.font; font.pixelSize: Math.max(9, Math.round(t.cw / 14))
                    wrapMode: Text.Wrap
                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                }
                Shimmer { anchors.fill: parent; running: true }
            }
        }
        NoImage { anchors.fill: parent; radius: t.radius; thumb: true; visible: !card.imgReady && card.noImg }
        // image in two fixed levels (240/480 px). If the tile size crosses the boundary (comparison/set progress
        // comes in), the level already loaded stays until the other is ready – otherwise the card would briefly be
        // blank at the start of the animation. A level once loaded stays loaded.
        readonly property bool needBig: t.cw > 160
        property bool wantS: !needBig
        property bool wantB: needBig
        onNeedBigChanged: if (needBig) wantB = true; else wantS = true
        readonly property bool okS: imgS.status === Image.Ready
        readonly property bool okB: imgB.status === Image.Ready
        readonly property Item img: needBig ? (okB || !okS ? imgB : imgS) : (okS || !okB ? imgS : imgB)
        readonly property bool imgReady: okS || okB
        Image {
            id: imgS
            anchors.fill: parent
            source: card.wantS && !t.pending ? t.img : ""
            asynchronous: true; cache: true
            smooth: true; mipmap: true
            fillMode: Image.PreserveAspectCrop
            verticalAlignment: Image.AlignTop
            sourceSize.width: 240
            visible: card.img === imgS && status === Image.Ready   // corners are rounded by quickimages when loading
            opacity: t.dim ? 0.45 : 1
        }
        Image {
            id: imgB
            anchors.fill: parent
            source: card.wantB && !t.pending ? t.img : ""
            asynchronous: true; cache: true
            smooth: true; mipmap: true
            fillMode: Image.PreserveAspectCrop
            verticalAlignment: Image.AlignTop
            sourceSize.width: 480
            visible: card.img === imgB && status === Image.Ready
            opacity: t.dim ? 0.45 : 1
        }
        // border of the selected card
        Rectangle {
            anchors.fill: parent
            visible: t.selected
            radius: t.radius
            color: "transparent"
            border.width: 2; border.color: T.accent
        }
        // checkmark (trade offer): on = bright, off = card dimmed
        Rectangle {
            visible: t.checkable
            anchors.right: parent.right; anchors.bottom: parent.bottom
            anchors.margins: Math.max(6, t.cw * 0.05)
            width: Math.max(22, t.cw * 0.14); height: width; radius: width * 0.28
            color: t.checked ? "#f2f2f2" : Qt.rgba(0.055, 0.055, 0.063, 0.86)
            border.width: 2; border.color: Qt.rgba(0, 0, 0, 0.85)   // dark outline: stands out on bright cards
            Text { anchors.centerIn: parent; text: "✓"; visible: t.checked; color: "#111111"
                   font.pixelSize: parent.width * 0.62; font.bold: true }
            TapHandler { gesturePolicy: TapHandler.ReleaseWithinBounds; onTapped: t.checkToggled() }
        }
        // in decks: small badge top left, mouse over = which decks (built = used up)
        // deck badge: only for cards in a deck (with its Canvas)
        Loader {
            active: t.decks.length > 0
            sourceComponent: Rectangle {
                id: deckBadge
                readonly property int bpx: Math.max(10, Math.min(14, Math.round(t.cw / 16)))
                x: t.cw * 0.098 - 2; y: t.ch * 0.125
                height: Math.round(bpx * 1.55); width: deckRow.implicitWidth + bpx * 0.9
                radius: 5
                color: Qt.rgba(0.055, 0.055, 0.063, 0.86)
                readonly property bool anyBuilt: { for (var i = 0; i < t.decks.length; i++) if (t.decks[i].built) return true; return false }
                Row {
                    id: deckRow
                    anchors.centerIn: parent
                    spacing: 3
                    Canvas {  // stack icon (two offset cards)
                        width: deckBadge.bpx; height: deckBadge.bpx
                        anchors.verticalCenter: parent.verticalCenter
                        onPaint: { var g = getContext("2d"); g.reset(); g.strokeStyle = "#f2f2f2"; g.lineWidth = 1.3
                            var s = width; g.strokeRect(s * 0.30, s * 0.10, s * 0.55, s * 0.68)
                            g.fillStyle = deckBadge.anyBuilt ? "#f2f2f2" : "rgba(0,0,0,0)"
                            g.beginPath(); g.rect(s * 0.12, s * 0.24, s * 0.55, s * 0.68); g.fill(); g.stroke() }
                    }
                    Text { text: t.decks.length; color: "#f2f2f2"; font.family: T.font; font.pixelSize: deckBadge.bpx; font.bold: true
                           anchors.verticalCenter: parent.verticalCenter }
                }
                HoverHandler {
                    onHoveredChanged: {
                        if (!hovered) { shell.tip("", 0, 0); return }
                        var lines = []
                        for (var i = 0; i < t.decks.length; i++) {
                            var d = t.decks[i]
                            lines.push("<b>" + d.deck + "</b> (" + d.n + "×)" + (d.built ? " · " + shell.text("built") : ""))
                        }
                        var p = deckBadge.mapToItem(null, deckBadge.width / 2, deckBadge.height)
                        shell.tip(shell.text("In your decks:") + "<br>" + lines.join("<br>"), p.x, p.y)
                    }
                }
            }
        }
        // chips: right-aligned, stacked in the image area
        Column {
            readonly property int bpx: Math.max(10, Math.min(14, Math.round(t.cw / 16)))
            id: chipCol
            anchors.right: parent.right
            anchors.rightMargin: t.cw * 0.098
            y: t.ch * 0.125
            spacing: 3
            Repeater {
                model: t.chips
                Rectangle {
                    required property string modelData
                    required property int index
                    visible: chipCol.y + (index + 1) * (height + 3) < t.ch * 0.56
                    anchors.right: parent.right
                    height: Math.round(chipCol.bpx * 1.55)
                    width: chipText.implicitWidth + chipCol.bpx * 0.9
                    radius: 5
                    color: Qt.rgba(0.055, 0.055, 0.063, 0.86)
                    Text {
                        id: chipText
                        anchors.centerIn: parent
                        text: modelData
                        color: "#f2f2f2"; font.family: T.font; font.pixelSize: chipCol.bpx; font.bold: true
                    }
                }
            }
        }
    }

    // condition: deliberately unlike the chips on the right (outlined, not filled, bottom left) – only if not NM
    Rectangle {
        visible: t.cond !== "" && t.ch > 60
        readonly property int bpx: Math.max(10, Math.min(13, Math.round(t.cw / 17)))
        x: card.x + t.cw * 0.09
        y: card.y + t.ch * 0.80 - height
        opacity: card.opacity
        height: Math.round(bpx * 1.6)
        width: condText.implicitWidth + bpx
        radius: height / 2
        color: Qt.rgba(0.04, 0.04, 0.045, 0.80)
        border.width: 1.2; border.color: "#f2f2f2"
        Text { id: condText; anchors.centerIn: parent; text: t.cond
               color: "#f2f2f2"; font.family: T.font; font.pixelSize: parent.bpx; font.bold: true; font.letterSpacing: 0.6 }
    }

    // name + price, the sets below
    Item {
        id: labels
        x: 8; width: t.width - 16
        y: card.y + t.ch + 5
        height: t.npx * 2.7
        opacity: t.a * t.txtA * t.selAA
        Text {
            id: priceText
            anchors.right: parent.right
            height: t.npx * 1.4
            verticalAlignment: Text.AlignVCenter
            text: t.price
            color: T.muted; font.family: T.font; font.pixelSize: t.npx - 1
        }
        Marquee {
            x: 0; width: parent.width - (t.price ? priceText.implicitWidth + 8 : 0)
            height: t.npx * 1.4
            text: t.name
            color: t.selected ? T.accent : (t.nameColor !== "" ? t.nameColor : T.text)
            px: t.npx; bold: true
            running: t.hv > 0.5
        }
        Marquee {
            y: t.npx * 1.4
            width: parent.width
            height: t.npx * 1.3
            text: t.setLine
            color: T.muted
            px: t.npx - 1
            running: t.hv > 0.5
        }
    }

    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
    // clicks and drags belong to the card itself (image + name) – the gap around it stays free for the grid's lasso
    Item { id: hit; x: 8; y: 6; width: t.width - 16; height: t.height - 12 }
    TapHandler {
        parent: hit
        // choosing (Ctrl/Shift, or cards are chosen): every tap counts – two quick ones on the same card are
        // "choose, unchoose", not a double click (otherwise the last card stayed chosen: Oliver's test of 0.9.2)
        property bool chose: false   // the run of taps began while choosing (it stays a choice, even at 0 chosen)
        function choosing() { return t.choosing }
        onTapped: function (ev, button) {
            if (tapCount === 1)
                chose = choosing()
            if (tapCount === 1 || chose || choosing()) {
                t.clickMods = point.modifiers
                t.clicked()
            }
        }
        onDoubleTapped: if (!chose && !choosing()) t.doubleClicked()
    }
    DragHandler {
        parent: hit
        enabled: t.draggable
        target: null
        dragThreshold: 12
        property point last
        onCentroidChanged: if (active) { last = centroid.scenePosition; t.dragMoved(last.x, last.y) }
        onActiveChanged: if (!active) t.dragEnded(last.x, last.y)
    }
}

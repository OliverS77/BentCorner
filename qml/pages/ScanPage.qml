// Scan page (stream window): camera image (texture, scaled on the GPU), on top the stream overlay
// (same drawing logic as before, as an image) and the windows „Find/edit card“, „Stream info“,
// „Stats“ and „Quick settings“ – all without a bridge. Mouse and wheel go to the previous logic.
// Over the image the tiles (ScanTiles: scan, last hit, biggest hit, status, stats – a grid, movable, resizable,
// scantiles.py). At the bottom a dock like a tile: quick access ┃ Tiles ┃ Studio ┃ ?. The page is the stream: after a
// few seconds without the mouse the nav, the dock and the tiles' keys go (the tiles stay) – a move brings them back.
// Windows grow out of their key.
// Data: scanView (qscan.py), scanTiles (scantiles.py).
import QtQuick
import QtQuick.Effects
import "../components"

Item {
    id: page
    property string key
    readonly property var sp: scanView
    readonly property var st: studioView
    readonly property bool studio: st.on   // Scan Studio: contribute cards to the database (qstudio.py)
    readonly property string mode: studio ? "studio" : "normal"
    // the dock's tile drawer: the quick keys make room for the tiles (hide/show each), the grid shows
    property bool drawer: false
    property real dk: drawer && !studio ? 1 : 0
    Behavior on dk { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
    function setMode(m) {
        if (m === "studio" || page.studio) {   // the studio switches itself (with its animation); close the windows first
            if (!page.studio) {
                if (card.on) page.sp.closePanel("card")
                if (stats.on) page.sp.closePanel("stats")
                if (quick.on) page.sp.toggleQuick("")
                if (page.sp.frameEdit) page.sp.toggleFrameEdit()
            }
            if ((m === "studio") !== page.studio) page.st.toggle()
        }
        page.drawer = false
    }
    property real sk: studio ? 0 : 1        // scan buttons of the bar: 1 visible, 0 hidden (Studio)
    Behavior on sk { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
    onVisibleChanged: {
        if (visible) forceActiveFocus()   // back on the scan page: keys (F, N …) come here
        page.st.pageVisible(visible)      // leaving the page: Studio stays open and rests, back = carry straight on
        scanTiles.setActive(visible)
    }
    // origin for the windows growing out (centre of the pressed key, in page coordinates)
    property real ox: width / 2
    property real oy: height - 50
    function originFrom(item) { var p = item.mapToItem(page, item.width / 2, item.height / 2); ox = p.x; oy = p.y }

    LiveView { id: camView; anchors.fill: parent; lv: page.sp }   // camera image + overlay, mouse to the previous logic

    // frosted glass under the tiles (Oliver): Python hands over the camera image small and already blurred
    // (scanView.frostSource, ~1 ms per new frame); here it is only scaled like the camera image and shown where the
    // tiles are (a mask of their shapes). Capturing the live view itself into a texture cost almost a CPU core.
    Item {
        id: frost
        objectName: "frost"
        anchors.fill: parent
        z: 1
        visible: T.tile.frost && !page.studio && tiles.visible && page.sp.frostSource !== ""
        Item {   // the blurred camera image, placed exactly like the live one (canvas, crop)
            id: frostImg
            anchors.fill: parent
            visible: false
            Item {
                id: fcv
                x: page.sp.canvas.x; y: page.sp.canvas.y; width: page.sp.canvas.width; height: page.sp.canvas.height
                clip: true
                readonly property real kx: page.sp.viewRect.width > 0 ? width / page.sp.viewRect.width : 1
                readonly property real ky: page.sp.viewRect.height > 0 ? height / page.sp.viewRect.height : 1
                Image {
                    x: -page.sp.viewRect.x * fcv.kx; y: -page.sp.viewRect.y * fcv.ky
                    width: page.sp.frameSize.width * fcv.kx; height: page.sp.frameSize.height * fcv.ky
                    source: page.sp.frostSource
                    cache: false; asynchronous: false; smooth: true; retainWhileLoading: true
                    fillMode: Image.Stretch
                }
            }
        }
        Item {   // the tiles' shapes (white = frosted)
            id: frostMask
            anchors.fill: parent
            visible: false
            layer.enabled: true
            Repeater {
                model: tiles.tiles
                Rectangle {
                    required property var modelData
                    x: modelData.x; y: modelData.y; width: modelData.width; height: modelData.height
                    radius: T.tile.radius; color: "#ffffff"; visible: modelData.visible
                }
            }
        }
        MultiEffect {
            anchors.fill: parent
            source: frostImg
            autoPaddingEnabled: false
            maskEnabled: true; maskSource: frostMask
        }
    }
    Component.onCompleted: scanTiles.setActive(visible)

    // the moments on top of everything (tiles, windows): the big preview of a card under the mouse, the Biggest Hit
    Image {
        anchors.fill: parent
        z: 20
        source: page.sp.fxSource
        visible: source !== ""
        cache: false; asynchronous: false; smooth: false; retainWhileLoading: true
    }

    // the tiles (not in the studio)
    ScanTiles {
        id: tiles
        anchors.fill: parent
        z: 2
        visible: !page.studio
        chrome: page.awake
        arrangeMode: page.drawer
        stage: page.sp.scanStage
        onDrawerWanted: page.drawer = true
    }

    // Like the navigation on top: every mouse movement brings the dock and the tiles' keys, after 3 s of stillness they
    // go (even when the mouse is on them – whoever adjusts something doesn't hold the mouse still). Open windows, the
    // tile drawer, a tile in hand keep them there.
    // only real movement counts – if the bar slides in under the still mouse, Qt reports that as „movement“ too
    property point lastMouse: Qt.point(-1, -1)
    function moved(p) { if (Math.abs(p.x - lastMouse.x) + Math.abs(p.y - lastMouse.y) > 2) { lastMouse = p; wake.restart() } }
    HoverHandler { id: anyMove; onPointChanged: page.moved(point.scenePosition) }
    Timer { id: wake; interval: T.tile.wakeMs; running: true }
    readonly property bool anyOpen: stats.on || card.on || quick.on || page.studio
    function focusIn(w) {   // is the keyboard focus inside this window?
        for (var it = page.Window.activeFocusItem; it; it = it.parent)
            if (it === w) return true
        return false
    }
    // one window at a time in the page: when one opens (card search/edit, camera, stats, keys), the others close
    function oneWindow(w) {
        if (w !== "card" && card.on) page.sp.closePanel("card")
        if (w !== "stats" && stats.on) page.sp.closePanel("stats")
        if (w !== "quick" && quick.on) page.sp.toggleQuick("")
        if (w !== "keys") keysSheet.visible = false
    }
    Connections { target: card; function onOnChanged() { if (card.on) page.oneWindow("card") } }
    Connections { target: stats; function onOnChanged() { if (stats.on) page.oneWindow("stats") } }
    Connections { target: quick; function onOnChanged() { if (quick.on) page.oneWindow("quick") } }
    Connections { target: keysSheet; function onVisibleChanged() { if (keysSheet.visible) page.oneWindow("keys") } }
    readonly property bool awake: wake.running || page.anyOpen || page.drawer || tiles.arranging || keysSheet.visible
                                  || page.sp.frameEdit
    MouseArea {   // quick settings open: clicking outside closes (like with the stats)
        anchors.fill: parent
        visible: quick.on && !page.sp.frameEdit
        z: 1
        acceptedButtons: Qt.AllButtons
        onPressed: page.sp.toggleQuick("")
    }

    // ---------- Windows of the scan page ----------
    component Panel: Rectangle {
        id: pn
        property var geo: ({})
        readonly property bool on: !!geo.shown
        // open/close: grows out of the bar's key (or shrinks back there); without animations instantly
        property real k: on ? 1 : 0
        property int dur: 300
        Behavior on k { enabled: shell.animate; NumberAnimation { duration: pn.dur * shell.speed; easing.type: Easing.OutCubic } }
        visible: on || k > 0.001
        opacity: Math.min(1, k * 1.4)
        x: geo.x || 0; y: geo.y || 0; width: geo.w || 0; height: geo.h || 0
        transform: Scale { origin.x: page.ox - pn.x; origin.y: page.oy - pn.y
                           xScale: 0.12 + 0.88 * pn.k; yScale: 0.12 + 0.88 * pn.k }
        radius: 16
        color: Qt.rgba(0.06, 0.06, 0.07, 1.0)
        border.width: 1; border.color: T.line2
        // clicks stay in the window (don't go to the overlay below)
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; hoverEnabled: true; onWheel: function (w) { w.accepted = true } }
        // closed: focus back to the page – otherwise „F“ & co. keep typing into an invisible field
        onOnChanged: if (!on) page.forceActiveFocus()
        // the content: built only while open (or closing), then kept 60 s – reopening stays instant
        property Component body: null
        readonly property Item bodyItem: bodyLd.item
        property bool warm: false
        onVisibleChanged: if (visible) { warm = true; cool.stop() } else cool.restart()
        Timer { id: cool; interval: 60000; onTriggered: pn.warm = false }
        Loader { id: bodyLd; anchors.fill: parent; active: pn.visible || pn.warm; sourceComponent: pn.body }
    }
    Panel {
        id: stats
        z: 2
        geo: page.sp.statsPanel
        body: Item { Flickable {
            id: statsMF
            ScrollHint {}
            anchors.fill: parent; anchors.margins: 18
            contentWidth: width; contentHeight: statsM.height; clip: true; boundsBehavior: Flickable.StopAtBounds
            Mirror { id: statsM; width: statsMF.width; mirror: page.sp.statsForm }
        } }
    }
    Panel {   // the camera, from the dock key – above the dock. No boxes inside: an ✕ top right, the settings below
        id: quick
        z: 2
        readonly property real qw: Math.min(page.width - 40, 460)
        readonly property real qh: 12 + 34 + 3 * 40 + 14   // fixed rows (from the content it would loop: geo -> body -> geo)
        geo: ({"shown": page.sp.quickOpen, "w": qw, "h": qh, "x": (page.width - qw) / 2,
               "y": page.height - 92 - qh})
        body: Item {
            component CamLine: Rectangle { width: parent ? parent.width : 0; height: T.tile.line; color: Qt.rgba(1, 1, 1, 0.09) }
            component CamKey: Text {   // a quiet text action / a switch: lit = on (selection = brightness, no boxes)
                id: ck
                property bool on: false
                property bool toggle: false
                signal clicked()
                color: toggle ? (on ? T.top : (ckm.containsMouse ? T.text : T.dim)) : (ckm.containsMouse ? T.top : T.text)
                font.family: T.font; font.pixelSize: 14; font.bold: toggle && on
                MouseArea { id: ckm; anchors.fill: parent; anchors.margins: -5; hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor; onClicked: ck.clicked() }
            }
            component CamRow: Item {
                property string label
                default property alias value: slot.data
                width: parent ? parent.width : 0; height: 40
                CamLine { anchors.top: parent.top }
                Text { anchors.verticalCenter: parent.verticalCenter; text: parent.label; color: T.muted
                       font.family: T.font; font.pixelSize: 13 }
                Row { id: slot; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: 18 }
            }
            Column {
                id: camCol
                x: 18; y: 12; width: quick.qw - 36   // not the parent's: its height sets the window's size
                spacing: 0
                Item {
                    width: parent.width; height: 34
                    Text { anchors.verticalCenter: parent.verticalCenter; text: shell.text("Camera").toUpperCase()
                           color: T.muted; font.family: T.font; font.pixelSize: 10; font.letterSpacing: 1.4 }
                    CamKey { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; text: "✕"
                             font.pixelSize: 15; onClicked: page.sp.toggleQuick("") }
                }
                CamRow {
                    label: shell.text("Device")
                    CamKey { text: (page.sp.cameraName || shell.text("no camera")) + "  ›"; enabled: page.sp.cameraName !== ""
                             onClicked: page.sp.pickCamera() }
                    CamKey { text: "↻"; font.pixelSize: 16; onClicked: page.sp.rescanCameras()
                             MouseArea { anchors.fill: parent; acceptedButtons: Qt.NoButton; hoverEnabled: true
                                         onContainsMouseChanged: containsMouse
                                             ? shell.tip(shell.text("Search for cameras again and reconnect"),
                                                         parent.mapToItem(null, parent.width / 2, parent.height).x,
                                                         parent.mapToItem(null, 0, parent.height).y)
                                             : shell.tip("", 0, 0) } }
                }
                CamRow {
                    label: shell.text("Mirror")
                    CamKey { toggle: true; on: page.sp.mirrorH; text: shell.text("horizontal ↔")
                             onClicked: page.sp.setMirror("h", !on) }
                    CamKey { toggle: true; on: page.sp.mirrorV; text: shell.text("vertical ↕")
                             onClicked: page.sp.setMirror("v", !on) }
                }
                Item {
                    width: parent.width; height: 40
                    CamLine { anchors.top: parent.top }
                    Text { anchors.verticalCenter: parent.verticalCenter; width: parent.width - more.width - 12
                           elide: Text.ElideRight; color: T.dim; font.family: T.font; font.pixelSize: 12
                           text: shell.text("Off after 1 min on another page") }
                    CamKey { id: more; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                             text: shell.text("All scan settings →"); onClicked: page.sp.scanSettings() }
                }
            }
        }
    }
    Panel {
        id: card
        z: 2
        // its place is taken when it opens and kept: only a new page size or search <-> edit moves it (Oliver's 0.9.2
        // test: the search window wobbled up and down the whole time); closed and opened again within a moment it
        // stays where it is
        readonly property var live: page.sp.cardPanel
        property var held: ({})
        geo: held
        onLiveChanged: {
            // closed: the keys (F …) go back to the page at once – not only once it has faded out, else a key pressed
            // right after Esc types into the fading search field
            if (!live.shown && page.focusIn(card)) page.forceActiveFocus()
            take()
        }
        function take() {
            var g = live
            if (!g.shown) {
                if (held.shown && !closing.running) closing.restart()
                return
            }
            closing.stop()
            if (!held.shown || g.mode !== held.mode || page.width !== held.pw || page.height !== held.ph)
                held = Object.assign({ pw: page.width, ph: page.height }, g)
        }
        Timer { id: closing; interval: 150
                onTriggered: if (!card.live.shown) card.held = Object.assign({}, card.held, { shown: false }) }
        // search: rises out of the bar (like the bar's other windows); edit: slides out sideways next to
        // the pack list and fades in meanwhile. The pack list stays in place.
        readonly property bool editMode: (geo.mode || "add") === "edit"
        dur: 320
        transform: []
        x: (geo.x || 0) + (editMode ? (1 - k) * (geo.fromLeft ? -60 : 60) : 0)
        y: (geo.y || 0) + (editMode ? 0 : (1 - k) * 80)
        scale: editMode ? 1 : 0.94 + 0.06 * k
        transformOrigin: Item.Bottom
        opacity: k
        body: Item { CardSearch {
            anchors.fill: parent; anchors.margins: 14
            cs: page.sp.cardSearch
            onCloseRequested: page.sp.closePanel("card")
        } }
    }

    // ---------- Scan Studio: camera & guide left, package & upload right – slide in from the sides ----------
    component StudioSide: Rectangle {
        id: sd
        property bool fromLeft: true
        property var form
        property Component header: null   // right column: large card image above the form
        property real k: page.studio ? 1 : 0
        Behavior on k { enabled: shell.animate; NumberAnimation { duration: 380 * shell.speed; easing.type: Easing.OutCubic } }
        visible: k > 0.001
        width: Math.min(fromLeft ? 340 : 420, page.width * 0.3)
        readonly property real gap: 14
        y: 56 + gap; height: page.height - 56 - 2 * gap
        x: fromLeft ? 20 - (1 - k) * (width + 40) : page.width - width - 20 + (1 - k) * (width + 40)
        opacity: Math.min(1, k * 1.3)
        z: 4
        radius: 16
        color: Qt.rgba(0.06, 0.06, 0.07, 0.94)
        border.width: 1; border.color: T.line2
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; hoverEnabled: true; onWheel: function (w) { w.accepted = true } }
        Loader {   // the content only while the studio is shown (or sliding)
            anchors.fill: parent
            active: sd.visible
            sourceComponent: Item { Flickable {
            id: sdF
            ScrollHint {}
            anchors.fill: parent; anchors.margins: 18
            contentWidth: width; contentHeight: sdCol.height; clip: true; boundsBehavior: Flickable.StopAtBounds
            Column {
                id: sdCol
                width: sdF.width - 14   // space on the right for the scroll bar – nothing runs under it
                spacing: 14
                Loader { width: parent.width; sourceComponent: sd.header; active: sd.header !== null }
                Mirror { id: sdM; width: sdCol.width; mirror: sd.form }
            }
            } }
        }
    }
    StudioSide { fromLeft: true; form: page.st.leftForm }
    StudioSide { id: rightSide; fromLeft: false; form: page.st.rightForm; header: cardSlot }
    // current card: large image – or an empty card mask; hover shows it large in the centre
    Component {
        id: cardSlot
        Item {
            id: slotRoot
            height: slotCard.height + 4
            Rectangle {
                id: slotCard
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(parent.width * 0.62, 250); height: width * 88 / 63
                radius: width * 0.045
                color: "transparent"
                border.width: page.st.frontUrl === "" ? 1.5 : 0
                border.color: Qt.rgba(1, 1, 1, 0.22)
                Image {
                    id: slotImg
                    anchors.fill: parent
                    opacity: page.st.viewingSent ? 0.55 : 1
                    source: page.st.frontUrl
                    fillMode: Image.PreserveAspectFit
                    smooth: true; mipmap: true
                    visible: source !== ""
                }
                Column {   // empty mask
                    visible: page.st.frontUrl === ""
                    anchors.centerIn: parent
                    spacing: 6
                    Text { anchors.horizontalCenter: parent.horizontalCenter; width: slotCard.width - 30
                           horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
                           text: shell.text("Put a card in view")
                           color: T.dim; font.family: T.font; font.pixelSize: 12 }
                }
                HoverHandler { id: slotHover; enabled: page.st.frontUrl !== "" }
                Binding { target: bigCard; property: "show"; value: slotHover.hovered }
                Component.onCompleted: page.slotItem = slotCard
                Component.onDestruction: if (page.slotItem === slotCard) page.slotItem = null   // studio closed
            }
        }
    }
    property Item slotItem: null
    Image {   // card image large (on hover over the card on the right)
        id: bigCard
        property bool show: false
        z: 7
        source: page.st.frontUrl
        visible: opacity > 0.01 && source !== ""
        opacity: show ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 160 } }
        fillMode: Image.PreserveAspectFit
        smooth: true; mipmap: true
        height: Math.min(page.height - 140, 900); width: height * 63 / 88
        anchors.centerIn: parent
    }

    // ---------- Box + Sent: two buttons left of the right column, sharing one window ----------
    component DockBtn: Rectangle {
        id: db
        property bool on: false
        property alias hovered: dbArea.containsMouse
        property real bump: 1
        signal clicked()
        z: 5
        visible: rightSide.k > 0.01
        opacity: rightSide.k
        height: 42
        y: bar.y - height - 12   // above the bottom bar
        radius: height / 2
        color: Qt.rgba(0.03, 0.03, 0.035, 0.82)
        border.width: 1; border.color: on ? Qt.rgba(1, 1, 1, 0.35) : (dbArea.containsMouse ? Qt.rgba(1, 1, 1, 0.18) : Qt.rgba(1, 1, 1, 0.08))
        scale: bump
        Behavior on bump { NumberAnimation { duration: 180; easing.type: Easing.OutBack } }
        MouseArea { id: dbArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: db.clicked() }
    }
    DockBtn {
        id: boxBtn
        width: 84
        x: page.width - Math.min(420, page.width * 0.3) - 20 - width - 14   // left of the right column
        on: page.st.boxOpen && page.st.boxTab === "box"
        onClicked: page.st.toggleBox()
        // flaps: 0 = almost closed (slightly open), 1 = fully open; hover lifts them a bit, wobbles briefly
        property real lid: on ? 1 : (hovered ? 0.45 : 0.12)
        Behavior on lid { NumberAnimation { duration: 320; easing.type: Easing.OutBack; easing.overshoot: 2.2 } }
        onLidChanged: boxIcon.requestPaint()
        Row {
            anchors.centerIn: parent
            spacing: 10
            Canvas {   // carton from the front, two flaps on top
                id: boxIcon
                width: 28; height: 26
                anchors.verticalCenter: parent.verticalCenter
                onPaint: {
                    var g = getContext("2d"); g.reset()
                    var hot = boxBtn.hovered || boxBtn.on
                    g.strokeStyle = hot ? "#ffffff" : "#cfcfcf"; g.lineWidth = 1.6; g.lineJoin = "round"; g.lineCap = "round"
                    g.strokeRect(5, 12, 18, 12)
                    // flaps rotate around the top edges: closed = horizontal over the opening, open = angled outwards
                    var a = (0.08 + 0.92 * boxBtn.lid) * 2.3, len = 9
                    g.beginPath()
                    g.moveTo(5, 12); g.lineTo(5 + Math.cos(a) * len, 12 - Math.sin(a) * len)       // left flap
                    g.moveTo(23, 12); g.lineTo(23 - Math.cos(a) * len, 12 - Math.sin(a) * len)     // right flap
                    g.stroke()
                }
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: page.st.boxCount
                color: "#f2f2f2"; font.family: T.font; font.pixelSize: 18; font.bold: true
            }
        }
    }
    DockBtn {   // Sent: paper plane
        id: sentBtn
        width: 60
        x: boxBtn.x - width - 10
        on: page.st.boxOpen && page.st.boxTab === "sent"
        onClicked: page.st.toggleSent()
        Item {
            id: planeBox
            anchors.fill: parent
            clip: true
            Canvas {
                id: plane
                width: 26; height: 22
                property real fx: 0; property real fy: 0; property real bob: 0
                x: (parent.width - width) / 2 + fx
                y: (parent.height - height) / 2 + fy + bob
                rotation: sentBtn.hovered && !flyAway.running ? -8 : 0
                Behavior on rotation { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
                SequentialAnimation on bob {   // bobs gently up and down on hover
                    running: sentBtn.hovered && !flyAway.running && shell.animate; loops: Animation.Infinite   // „Performance“: calm
                    NumberAnimation { to: -2.5; duration: 380; easing.type: Easing.InOutSine }
                    NumberAnimation { to: 1.5; duration: 380; easing.type: Easing.InOutSine }
                    onStopped: plane.bob = 0
                }
                onPaint: {
                    var g = getContext("2d"); g.reset()
                    g.strokeStyle = sentBtn.hovered || sentBtn.on ? "#ffffff" : "#cfcfcf"; g.lineWidth = 1.5; g.lineJoin = "round"
                    g.beginPath(); g.moveTo(1, 10); g.lineTo(25, 1); g.lineTo(18, 21); g.lineTo(12, 13); g.closePath(); g.stroke()
                    g.beginPath(); g.moveTo(25, 1); g.lineTo(12, 13); g.lineTo(11, 20); g.lineTo(15, 16); g.stroke()
                }
                Connections { target: sentBtn; function onHoveredChanged() { plane.requestPaint() } function onOnChanged() { plane.requestPaint() } }
            }
        }
        // uploaded: the plane whooshes off to the top right and glides back in from the left
        SequentialAnimation {
            id: flyAway
            ParallelAnimation {
                NumberAnimation { target: plane; property: "fx"; to: 46; duration: 420; easing.type: Easing.InCubic }
                NumberAnimation { target: plane; property: "fy"; to: -30; duration: 420; easing.type: Easing.InCubic }
            }
            PropertyAction { target: plane; property: "fx"; value: -50 }
            PropertyAction { target: plane; property: "fy"; value: 8 }
            PauseAnimation { duration: 160 }
            ParallelAnimation {
                NumberAnimation { target: plane; property: "fx"; to: 0; duration: 520; easing.type: Easing.OutBack }
                NumberAnimation { target: plane; property: "fy"; to: 0; duration: 520; easing.type: Easing.OutCubic }
            }
            ScriptAction { script: { sentBtn.bump = 1.15; sentBack.restart() } }
        }
        Timer { id: sentBack; interval: 170; onTriggered: sentBtn.bump = 1 }
        Connections { target: page.st; function onSentAway() { if (shell.animate) flyAway.restart() } }
        Rectangle {   // number of cards sent
            visible: page.st.sentCount > 0
            anchors.right: parent.right; anchors.top: parent.top; anchors.rightMargin: -4; anchors.topMargin: -4
            width: Math.max(18, sc.implicitWidth + 8); height: 18; radius: 9
            color: "#2a2a2c"; border.width: 1; border.color: Qt.rgba(1, 1, 1, 0.18)
            Text { id: sc; anchors.centerIn: parent; text: page.st.sentCount > 99 ? "99+" : page.st.sentCount
                   color: "#dcdcdc"; font.family: T.font; font.pixelSize: 10; font.bold: true }
        }
    }
    Image {   // card flies into the box
        id: flyer
        z: 8
        visible: false
        fillMode: Image.PreserveAspectFit
        property real fromX: 0; property real fromY: 0
        ParallelAnimation {
            id: flyAnim
            NumberAnimation { target: flyer; property: "x"; from: flyer.fromX; to: boxBtn.x + boxBtn.width / 2 - flyer.width * 0.5
                              duration: 480; easing.type: Easing.InOutCubic }
            NumberAnimation { target: flyer; property: "y"; from: flyer.fromY; to: boxBtn.y + boxBtn.height / 2 - flyer.height * 0.5
                              duration: 480; easing.type: Easing.InCubic }
            NumberAnimation { target: flyer; property: "scale"; from: 1; to: 0.18; duration: 480; easing.type: Easing.InCubic }
            NumberAnimation { target: flyer; property: "rotation"; from: 0; to: -14; duration: 480 }
            onFinished: { flyer.visible = false; boxBtn.bump = 1.18; bumpBack.restart() }
        }
        Timer { id: bumpBack; interval: 170; onTriggered: boxBtn.bump = 1 }
        Connections {
            target: page.st
            function onFlyToBox(url) {
                var s = page.slotItem
                if (!s || !shell.animate) { boxBtn.bump = 1.18; bumpBack.restart(); return }
                var p = s.mapToItem(page, 0, 0)
                flyer.width = s.width; flyer.height = s.height
                flyer.fromX = p.x; flyer.fromY = p.y
                flyer.source = url; flyer.visible = true
                flyAnim.restart()
            }
        }
    }
    Rectangle {   // opened box
        id: boxPanel
        z: 6
        property real k: page.st.boxOpen && page.studio ? 1 : 0
        Behavior on k { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }
        visible: k > 0.01
        opacity: k
        transform: Scale { origin.x: boxPanel.anchorBtn.x + boxPanel.anchorBtn.width / 2 - boxPanel.x; origin.y: boxPanel.height
                           xScale: 0.85 + 0.15 * boxPanel.k; yScale: 0.85 + 0.15 * boxPanel.k }
        width: Math.min(500, page.width * 0.4)
        readonly property Item anchorBtn: sent ? sentBtn : boxBtn
        x: Math.max(20, anchorBtn.x + anchorBtn.width - width)
        height: Math.min(page.height - 56 - 40 - bar.height - 24, boxCol.implicitHeight + 32)
        y: boxBtn.y - height - 12
        radius: 16
        color: Qt.rgba(0.06, 0.06, 0.07, 0.97)
        border.width: 1; border.color: T.line2
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; hoverEnabled: true; onWheel: function (w) { w.accepted = true } }
        readonly property bool sent: page.st.boxTab === "sent"
        Column {
            id: boxCol
            x: 16; y: 16; width: parent.width - 32
            spacing: 12
            Text {
                text: boxPanel.sent ? shell.text("Sent") : shell.text("In the box") + " (" + page.st.boxCount + ")"
                color: T.text2; font.family: T.font; font.pixelSize: 14; font.bold: true
            }
            ListView {
                id: boxList
                width: parent.width
                height: Math.min(contentHeight, page.height * 0.34)
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                spacing: 4
                model: boxPanel.sent ? page.st.sentItems : page.st.boxItems
                ScrollHint {}
                delegate: Rectangle {
                    required property var modelData
                    readonly property var it: modelData
                    width: boxList.width
                    height: it.head ? 30 : 64
                    radius: 10
                    color: it.editing || (boxPanel.sent && it.pid === page.st.viewingPid) ? Qt.rgba(1, 1, 1, 0.10)
                           : (rowHover.hovered && !it.head ? Qt.rgba(1, 1, 1, 0.05) : "transparent")
                    HoverHandler { id: rowHover }
                    Text { visible: !!it.head; anchors.verticalCenter: parent.verticalCenter; x: 4
                           text: it.title + "  ·  " + it.sub; color: T.dim; font.family: T.font; font.pixelSize: 12; font.bold: true }
                    Image {
                        id: rowImg
                        visible: !it.head
                        x: 6; anchors.verticalCenter: parent.verticalCenter
                        height: 56; width: 40
                        fillMode: Image.PreserveAspectFit
                        source: it.url || ""
                        smooth: true; mipmap: true
                    }
                    Column {
                        visible: !it.head
                        x: 56; anchors.verticalCenter: parent.verticalCenter
                        width: parent.width - 56 - 44
                        spacing: 2
                        Text { width: parent.width; elide: Text.ElideRight; text: it.title
                               color: it.parked ? T.dim : T.text; font.family: T.font; font.pixelSize: 14; font.bold: true
                               font.italic: !!it.parked }
                        Text { width: parent.width; elide: Text.ElideRight; text: it.sub
                               color: it.error ? "#ff8a8a" : T.dim; font.family: T.font; font.pixelSize: 12 }
                        Text { visible: !!it.note; width: parent.width; wrapMode: Text.WordWrap; text: it.note || ""
                               color: T.muted; font.family: T.font; font.pixelSize: 12; font.italic: true }
                    }
                    MouseArea {
                        anchors.fill: parent
                        enabled: !it.head
                        cursorShape: Qt.PointingHandCursor
                        onClicked: boxPanel.sent ? page.st.openSent(it.pid) : page.st.openItem(it.cid || "")
                    }
                    Btn {
                        visible: !it.head && !it.parked && (!boxPanel.sent || it.error)
                        anchors.right: parent.right; anchors.rightMargin: 4; anchors.verticalCenter: parent.verticalCenter
                        width: 34; height: 30; text: "✕"
                        tip: boxPanel.sent ? shell.text("Delete from this PC") : shell.text("Take out of the box")
                        onClicked: boxPanel.sent ? page.st.forget(it.pid) : page.st.removeItem(it.cid)
                    }
                }
            }
            Text {
                visible: boxList.count === 0
                text: boxPanel.sent ? shell.text("Nothing uploaded yet.")
                                    : shell.text("Still empty – capture a card, fill in the right side, “Into the box”.")
                color: T.dim; font.family: T.font; font.pixelSize: 13
            }
            Rectangle { width: parent.width; height: 1; color: T.line; visible: !boxPanel.sent }   // list | details
            Mirror { width: parent.width; mirror: page.st.boxForm }
        }
    }
    Shortcut { sequence: "Escape"; enabled: page.visible && page.st.boxOpen && !sheetHost.covering
               onActivated: page.st.toggleBox() }
    // new capture: briefly large at the top centre (the camera image stays), then slides right into the package
    Image {
        id: shotPeek
        property real k: 0
        z: 4
        visible: k > 0.001 && page.studio
        source: ""
        fillMode: Image.PreserveAspectFit
        height: Math.min(page.height * 0.42, 420); width: height * 0.72
        x: (page.width - width) / 2 + Math.max(0, k - 0.75) * 4 * page.width * 0.3
        y: 40
        opacity: k < 0.75 ? Math.min(1, k * 6) : 1 - (k - 0.75) * 4
        SequentialAnimation {
            id: peekAnim
            NumberAnimation { target: shotPeek; property: "k"; from: 0; to: 0.75; duration: 1600 }
            NumberAnimation { target: shotPeek; property: "k"; to: 1; duration: 380; easing.type: Easing.InCubic }
            PropertyAction { target: shotPeek; property: "k"; value: 0 }
        }
        Connections {
            target: page.st
            function onShotTaken(url) { shotPeek.source = url; peekAnim.restart() }
        }
    }

    // ---------- Dock at the bottom: like a tile (glass, rounded), in the middle where the bar was ----------
    // Quick access (with text) ┃ the three modes of the scan window – Normal · Stream ┃ Studio ┃ ? (keys). The strip
    // beside it stays free of tiles (the grid ends above it). Stream: slides away, a mouse move brings it back for a
    // moment (like the nav).
    Rectangle {
        id: bar
        readonly property bool awake: page.awake
        width: dockRow.width + 16; height: T.tile.bar - 12
        x: (page.width - width) / 2
        z: 5
        y: page.height - (awake ? height + 6 : -2)
        Behavior on y { NumberAnimation { duration: T.tile.fadeMs; easing.type: Easing.OutCubic } }
        opacity: awake ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: T.tile.fadeMs } }
        visible: opacity > 0.01
        radius: T.tile.radius
        color: Qt.rgba(0.06, 0.06, 0.065, T.tile.glassStream)
        border.width: 1; border.color: Qt.rgba(1, 1, 1, 0.09)
        HoverHandler { onPointChanged: page.moved(point.scenePosition) }
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; hoverEnabled: true   // nothing to the image
                    onPressed: forceActiveFocus() }   // an open field saves (like Enter)
        // a key of the dock: icon + text, no box (design rule) – on = bright (+ lamp), off = quieter, red = attention
        component BarItem: Item {
            id: bi
            property string icon: ""
            property bool tilesIcon: false     // the tile drawer's own sign (TilesIcon)
            property string text: ""
            property string tip: ""
            property bool on: false
            property bool lamp: false          // a switch/mode: lamp before the text
            property color alert: "transparent"
            signal clicked()
            width: biRow.implicitWidth + 20; height: bar.height
            opacity: enabled ? 1 : 0.4
            readonly property color ink: alert.a > 0 ? alert : (on ? T.top : (biMa.containsMouse ? T.text : T.text2))
            Row {
                id: biRow
                anchors.centerIn: parent
                spacing: 8
                Rectangle { visible: bi.lamp; width: 7; height: 7; radius: 3.5; anchors.verticalCenter: parent.verticalCenter
                            color: bi.on ? "#ffffff" : T.off }
                NavIcon { visible: bi.icon !== ""; anchors.verticalCenter: parent.verticalCenter; key: bi.icon; s: 0.85
                          color: bi.ink; play: biMa.containsMouse }
                TilesIcon { visible: bi.tilesIcon; anchors.verticalCenter: parent.verticalCenter; s: 0.9
                            color: bi.ink; play: biMa.containsMouse }
                Text { anchors.verticalCenter: parent.verticalCenter; text: bi.text; color: bi.ink
                       font.family: T.font; font.pixelSize: 13; font.bold: bi.on }
            }
            MouseArea {
                id: biMa
                anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                enabled: bi.enabled
                onPressed: forceActiveFocus()   // an open field saves first (like Enter)
                onClicked: bi.clicked()
                onContainsMouseChanged: containsMouse && bi.tip !== ""
                    ? shell.tip(bi.tip, bi.mapToItem(null, bi.width / 2, 0).x, bi.mapToItem(null, 0, 0).y - 34)
                    : shell.tip("", 0, 0)
            }
        }
        component BarLine: Rectangle { width: 1; height: 22; anchors.verticalCenter: parent ? parent.verticalCenter : undefined
                                       color: Qt.rgba(1, 1, 1, 0.12) }
        Row {
            id: dockRow
            anchors.centerIn: parent
            spacing: 0
            Item {   // quick access – in the Studio "Capture" takes its place (the dock follows the width)
                id: quickPart
                width: (barRow.implicitWidth * (1 - page.dk) + tilesRow.implicitWidth * page.dk) * page.sk
                       + (bShot.width + 16) * (1 - page.sk); height: bar.height
                clip: true
                Row {
                    id: barRow
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 0
                    opacity: page.sk * (1 - page.dk); visible: opacity > 0.01
                    BarItem { id: bPlay; enabled: !page.studio; icon: page.sp.paused ? "play" : "pause"
                              text: page.sp.paused ? shell.text("Resume") : shell.text("Pause")
                              alert: page.sp.paused ? "#ff5252" : "transparent"   // paused: red like camera off
                              tip: page.sp.paused ? shell.text("Resume scanning (Space)") : shell.text("Pause scanning (Space)")
                              onClicked: page.sp.togglePause() }
                    BarLine {}
                    BarItem { id: bSearch; enabled: !page.studio; icon: "search"; on: card.on; text: shell.text("Search card")
                              tip: shell.text("Search and add a card (K)")
                              onClicked: { page.originFrom(bSearch); page.sp.openPanel("search") } }
                    BarLine {}
                    BarItem { id: bFrame; enabled: !page.studio; icon: "frame"; text: shell.text("Scan frame")
                              alert: page.sp.frameEdit ? "#ff5252" : "transparent"
                              tip: page.sp.frameEdit ? shell.text("Hide the scan frame – click: done")
                                                     : shell.text("Show and adjust the scan frame (drag, wheel = size)")
                              onClicked: page.sp.toggleFrameEdit() }
                    BarLine {}
                    // one camera key: device, mirroring (it turns off by itself on other pages – no off switch)
                    BarItem { id: bQuick; enabled: !page.studio; icon: "camTune"; on: page.sp.quickMode === "cam"
                              text: shell.text("Camera")
                              tip: shell.text("Camera: device, mirroring")
                              onClicked: { page.originFrom(bQuick); page.sp.toggleQuick("cam") } }
                }
                Row {   // the tile drawer: every tile, lit = shown – a click hides / shows it
                    id: tilesRow
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 0
                    opacity: page.sk * page.dk; visible: opacity > 0.01
                    Repeater {
                        model: [{ k: "session", t: "Scan" }, { k: "hit", t: shell.text("Last hit") },
                                { k: "top", t: shell.text("Biggest hit") }, { k: "status", t: shell.text("Status") },
                                { k: "stats", t: shell.text("Stats") }]
                        BarItem {
                            required property var modelData
                            readonly property var ent: scanTiles.layout[modelData.k] || ({})
                            lamp: true; on: ent.shown !== false; text: modelData.t
                            tip: on ? shell.text("Shown – click: hide") : shell.text("Hidden – click: show")
                            onClicked: {
                                var t = tiles.tileOf(modelData.k)
                                scanTiles.setTileShown(modelData.k, !on, t.lim.minW, t.lim.minH)
                            }
                        }
                    }
                    BarLine {}
                    BarItem { text: shell.text("Reset"); tip: shell.text("Back to the first layout")
                              onClicked: scanTiles.resetLayout() }
                }
                Btn {
                    id: bShot
                    anchors.centerIn: parent
                    width: 420; height: 34
                    primary: true
                    opacity: 1 - page.sk; visible: opacity > 0.01; enabled: page.studio
                    text: shell.text("Capture now")
                    tip: shell.text("Capture the card (space) – the sharpest of the last frames, straightened")
                    onClicked: page.st.capture()
                }
            }
            Item {   // the tile drawer's key (not in the studio)
                width: bTiles.width * page.sk; height: bar.height; clip: true
                BarLine { anchors.left: parent.left; opacity: page.sk }
                BarItem { id: bTiles; x: 1; tilesIcon: true; lamp: true; on: page.drawer; opacity: page.sk
                          enabled: !page.studio; text: shell.text("Tiles")
                          tip: page.drawer ? shell.text("Done")
                                           : shell.text("Hide and show tiles – move a tile by dragging it anywhere, resize it at an edge")
                          onClicked: page.drawer = !page.drawer }
            }
            Rectangle { width: 1; height: 26; anchors.verticalCenter: parent.verticalCenter; color: Qt.rgba(1, 1, 1, 0.22) }
            BarItem { lamp: true; on: page.mode === "studio"; text: shell.text("Studio")
                      tip: page.studio ? shell.text("Back to scanning")
                                       : shell.text("Scan studio: contribute missing cards, better images or alt-arts to the "
                                                    + "database – nothing goes into your collection")
                      onClicked: page.setMode(page.studio ? "normal" : "studio") }
            BarLine {}
            BarItem { id: bKeys; on: keysSheet.visible; text: "?"
                      tip: shell.text("All keys of the scan page")
                      onClicked: keysSheet.visible = !keysSheet.visible }
        }
    }
    // the tile drawer's first opening: once, what the tiles are – in the dock's place (it grows upwards), no pop-up
    Rectangle {
        id: tilesHint
        readonly property bool on: page.drawer && !page.studio && scanTiles.view.tilesHint === true
        visible: on
        z: 5
        width: Math.max(bar.width, 520); height: hintCol.height + 28
        x: (page.width - width) / 2; y: bar.y - height - 8
        radius: T.tile.radius
        color: Qt.rgba(0.06, 0.06, 0.065, T.tile.glassStream)
        border.width: 1; border.color: Qt.rgba(1, 1, 1, 0.18)
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons }
        Column {
            id: hintCol
            x: 16; y: 14; width: parent.width - 32; spacing: 8
            Text { text: shell.text("Your tiles are windows"); color: T.text; font.family: T.display; font.pixelSize: 18
                   font.weight: Font.DemiBold }
            Text { width: parent.width; wrapMode: Text.WordWrap; color: T.text2; font.family: T.font; font.pixelSize: 13
                   text: shell.text("Put them where you like: drag a tile anywhere on its surface, pull an edge for its size. "
                                    + "Down here you switch tiles on and off – there are more than you see.") }
            Btn { text: shell.text("Got it"); compact: true; width: 120; height: 30; onClicked: scanTiles.tilesHintSeen() }
        }
    }
    // "? Keys": every key of the scan page, in the window (no pop-up)
    Rectangle {
        id: keysSheet
        visible: false
        z: 30
        anchors.centerIn: parent
        width: 720; height: (keysLd.item ? keysLd.item.implicitHeight : 0) + 48; radius: 18
        color: T.surface; border.width: 1; border.color: T.line2
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons }
        Loader {   // (built only while shown)
            id: keysLd
            x: 24; y: 24
            active: keysSheet.visible
            sourceComponent: keysComp
        }
    }
    Component {
        id: keysComp
        Column {
            id: keysCol
            width: 720 - 48; spacing: 0
            Text { text: shell.text("Keys while scanning"); color: T.text; font.family: T.display; font.pixelSize: 22; bottomPadding: 4 }
            Text { text: shell.text("They work while no window is open. Esc closes."); color: T.muted; font.family: T.font
                   font.pixelSize: 13; bottomPadding: 12 }
            Grid {
                columns: 2; columnSpacing: 36; width: parent.width
                Repeater {
                    model: [["Space", shell.text("Pause / resume")], ["K", shell.text("Search and add a card")],
                            ["N", shell.text("New pack (opening boosters)")],
                            ["E", shell.text("Edit the last card")], ["+", shell.text("Count the last card once more")],
                            ["F", shell.text("Next finish")], ["Z", shell.text("Next condition")],
                            ["U / Del", shell.text("Remove the last card")], ["G", shell.text("I give this away (trade scan)")],
                            ["B", shell.text("Open the library")], ["Esc", shell.text("Close window / scan frame")]]
                    Item {
                        required property var modelData
                        width: (keysCol.width - 36) / 2; height: 34
                        Rectangle { width: parent.width; height: 1; anchors.bottom: parent.bottom; color: T.line }
                        Rectangle { id: kb; anchors.verticalCenter: parent.verticalCenter; width: Math.max(44, kt.implicitWidth + 14); height: 22; radius: 5
                                    color: "transparent"; border.width: 1; border.color: T.line2
                                    Text { id: kt; anchors.centerIn: parent; text: modelData[0]; color: T.text; font.family: T.font; font.pixelSize: 11 } }
                        Text { x: kb.width + 14; anchors.verticalCenter: parent.verticalCenter; text: modelData[1]; color: T.text2
                               font.family: T.font; font.pixelSize: 13 }
                    }
                }
            }
        }
    }
    Text {   // set up scan frame: short guide on top
        visible: page.sp.frameEdit
        anchors.horizontalCenter: parent.horizontalCenter; y: 80
        text: shell.text("Drag the scan frame · mouse wheel over it = size")
        color: "#f2f2f2"; style: Text.Outline; styleColor: "#000000"
        font.family: T.font; font.pixelSize: 15; font.bold: true
    }

    // keyboard shortcuts of the scan page (the old ones only apply in Qt Widgets windows)
    Repeater {
        model: ["N", "U", "Delete", "F", "Z", "G", "Space", "E", "K", "B", "+"]
        Item {
            required property string modelData
            Shortcut {
                sequence: modelData
                enabled: page.visible && !sheetHost.covering && !card.live.shown && !quick.on
                context: Qt.WindowShortcut
                onActivated: page.sp.key(modelData)
            }
        }
    }
    // the scanner's question open and its field not focused (clicked elsewhere in the window): F still switches the
    // finish there (in the field the field's own key hook does it)
    Shortcut { sequence: "F"; context: Qt.WindowShortcut
               enabled: page.visible && card.visible && !sheetHost.covering && page.sp.cardSearch.questionKind !== ""
               onActivated: page.sp.cardSearch.nextFinish() }
    Shortcut { sequence: "Escape"; enabled: page.visible && keysSheet.visible; onActivated: keysSheet.visible = false }
    Shortcut { sequence: "Escape"; enabled: page.visible && page.drawer && !keysSheet.visible; onActivated: page.drawer = false }
    Shortcut { sequence: "Escape"; enabled: page.visible && page.studio && !page.st.boxOpen && !sheetHost.covering
               onActivated: page.st.toggle() }
    Shortcut { sequence: "Escape"; enabled: page.visible && card.visible; onActivated: page.sp.closePanel("card") }
    Shortcut { sequence: "Escape"; enabled: page.visible && !card.visible && stats.visible && !sheetHost.covering
               onActivated: page.sp.closePanel("stats") }
    Shortcut { sequence: "Escape"; enabled: page.visible && quick.visible && !sheetHost.covering
               onActivated: page.sp.toggleQuick("") }
    Shortcut { sequence: "Escape"; enabled: page.visible && page.sp.frameEdit && !quick.visible
               onActivated: page.sp.toggleFrameEdit() }
    // ticket mode: hint
    Rectangle {
        visible: page.sp.ticketMode
        anchors.centerIn: parent
        width: 420; height: 150; radius: 16
        color: Qt.rgba(0.05, 0.05, 0.055, 0.92); border.width: 1; border.color: T.line2
        z: 30
        Column {
            anchors.centerIn: parent
            spacing: 12
            Text { anchors.horizontalCenter: parent.horizontalCenter
                   text: shell.text("Scan trade ticket")
                   color: T.text; font.family: T.display; font.pixelSize: 24 }
            Text { anchors.horizontalCenter: parent.horizontalCenter; width: 380; horizontalAlignment: Text.AlignHCenter
                   wrapMode: Text.WordWrap; color: T.muted; font.family: T.font; font.pixelSize: 13
                   text: shell.text("Hold the ticket in the frame – e.g. the image on your phone.") }
            Btn { anchors.horizontalCenter: parent.horizontalCenter; height: 36; width: 200; primary: true
                  text: shell.text("Cancel")
                  onClicked: page.sp.cancelTicket() }
        }
    }
}

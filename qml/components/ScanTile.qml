// One tile of the scan page (ui/scantiles.py): glass over the camera image – frosted: the page blurs the camera image
// once per frame under all tiles (ScanPage: frost), the tile lays its tint on top. Head: title · the tile drawer's key. Moved by pressing anywhere that
// isn't a field or a key and dragging (no grip), resized at the right edge (width), the bottom edge (height) or the
// bottom right corner (both) – always in grid steps, never below nor above what its content needs (ScanTiles.lim); a
// smaller stored size grows to it (scanTiles.fitTile). scantiles stores the place (or refuses it, then the tile goes
// back). Hovering the tile thickens its bottom right corner a little: the hint where it grows. A few seconds without
// the mouse (grid.chrome off): the key and the grips go – the page is the stream. One-row tiles (height 1) have no
// head row: the content, the key on the right.
import QtQuick

Item {
    id: tl
    property string key
    property string title
    property var ent: ({ c: 0, r: 0, w: 4, h: 2 })
    property var grid                       // ScanTiles: cell size, origin, arranging, chrome
    readonly property bool compact: ent.h <= 1
    readonly property bool controls: grid.chrome || moving || sizing
    default property alias content: body.data
    property bool tight: false              // hit tiles: a narrow edge, the content (the card) fills the tile
    readonly property real padX: tight ? 6 : T.tile.pad

    // ---- moving / resizing (live, before it snaps) ----
    property bool moving: false
    property point mv: Qt.point(0, 0)       // moving: how far it is dragged (pixels)
    readonly property bool sizing: rzR.pressed || rzB.pressed || rzC.pressed
    readonly property var lim: grid.lim(key)   // {minW, maxW, minH, midH, maxH} in cells – what the content needs
    property real dw: 0     // resize: extra width/height while pulling (pixels)
    property real dh: 0
    readonly property real gap: T.tile.gap
    // always inside the visible grid: a tile wider/taller than its stored place allows (its content's minimum after a
    // window change, full screen …) moves left/up instead of running past the window's edge
    readonly property real rawX: grid.x0 + ent.c * grid.cw + gap / 2
    readonly property real rawY: grid.y0 + ent.r * grid.ch + gap / 2
    readonly property real baseX: grid.cw > 0 ? Math.max(grid.x0 + gap / 2,
                                                  Math.min(rawX, grid.x0 + grid.cols * grid.cw - gap / 2 - width)) : rawX
    readonly property real baseY: grid.ch > 0 ? Math.max(grid.y0 + gap / 2,
                                                  Math.min(rawY, grid.y0 + grid.rows * grid.ch - gap / 2 - height)) : rawY
    x: baseX + (moving ? mv.x : 0)
    y: baseY + (moving ? mv.y : 0)
    // while pulling: live, but never past what the content allows (lim)
    // shown: never bigger than the content needs, even when a bigger size is stored (older layouts, a content that
    // shrank – boosters -> cards), never smaller than it needs (the stored size grows, fitTile); pulling starts from
    // what is shown
    readonly property int sw: Math.max(lim.minW, Math.min(ent.w, lim.maxW, grid.cols))
    readonly property int sh: Math.max(lim.minH, Math.min(ent.h, lim.maxH, grid.rows))
    width: Math.max(lim.minW * grid.cw - gap, Math.min(lim.maxW * grid.cw - gap, sw * grid.cw - gap + dw))
    height: Math.max(lim.minH * grid.ch - gap, Math.min(lim.maxH * grid.ch - gap, sh * grid.ch - gap + dh))
    z: moving || sizing ? 6 : 1
    readonly property bool shown: ent.shown !== false     // the dock's tile drawer hides tiles
    // the card search's big preview stands where this tile is (scanView.previewStrip): fade out softly meanwhile
    readonly property var strip: scanView.previewStrip || ({})
    // … and where the open card search itself covers the tile (small windows): never half covered – faded out
    readonly property var panel: scanView.cardPanel || ({})
    readonly property bool underPanel: panel.shown === true && x < panel.x + panel.w && x + width > panel.x
                                       && y < panel.y + panel.h && y + height > panel.y
    readonly property bool hushed: (strip.x1 !== undefined && x < strip.x1 && x + width > strip.x0) || underPanel
    opacity: hushed ? 0 : 1
    Behavior on opacity { NumberAnimation { duration: T.tile.fadeMs } }
    visible: shown && opacity > 0.01
    // a stored size below the minimum (older layouts, a bigger window before): stored bigger – once the grid has a size
    function fitNow() { if (shown && grid.cw > 0 && grid.ch > 0 && (ent.w < lim.minW || ent.h < lim.minH)) fitT.restart() }
    Timer { id: fitT; interval: 400; onTriggered: if (!tl.moving && !tl.sizing) scanTiles.fitTile(tl.key, tl.lim.minW, tl.lim.minH) }
    onLimChanged: fitNow()
    onEntChanged: fitNow()
    Component.onCompleted: fitNow()
    // where it would snap now (the dashed ghost of ScanTiles shows it)
    readonly property int tc: Math.max(0, Math.min(grid.cols - sw, Math.round((x - grid.x0 - gap / 2) / grid.cw)))
    readonly property int trow: Math.max(0, Math.min(grid.rows - sh, Math.round((y - grid.y0 - gap / 2) / grid.ch)))
    readonly property int tw: Math.max(lim.minW, Math.min(lim.maxW, grid.cols - ent.c, Math.round((width + gap) / grid.cw)))
    readonly property int th: Math.min(grid.rows - ent.r, grid.snapH(key, Math.round((height + gap) / grid.ch)))

    Rectangle {   // the glass
        anchors.fill: parent
        radius: T.tile.radius
        color: Qt.rgba(0.06, 0.06, 0.065, tl.grid.tint !== undefined ? tl.grid.tint : T.tile.glass)
        border.width: 1
        border.color: tl.moving || tl.sizing ? Qt.rgba(1, 1, 1, 0.5) : Qt.rgba(1, 1, 1, 0.09)
    }
    // the tile's ground: swallows clicks (they must not reach the camera image / overlay below); a click beside a
    // field takes the focus, so an open field saves (like Enter); pressing and dragging moves the tile (fields, keys
    // and lists on top keep their own presses)
    MouseArea {
        id: ground
        anchors.fill: parent; acceptedButtons: Qt.AllButtons; hoverEnabled: true
        cursorShape: tl.moving ? Qt.ClosedHandCursor : (tl.controls ? Qt.OpenHandCursor : Qt.ArrowCursor)
        property point p0
        onPressed: function (m) { forceActiveFocus(); p0 = mapToItem(null, m.x, m.y) }
        onPositionChanged: function (m) {
            if (!pressed || !(m.buttons & Qt.LeftButton) || !tl.controls) return
            var p = mapToItem(null, m.x, m.y)
            if (!tl.moving && Math.abs(p.x - p0.x) + Math.abs(p.y - p0.y) < 6) return   // a click, not a drag
            tl.mv = Qt.point(p.x - p0.x, p.y - p0.y)
            if (!tl.moving) { tl.moving = true; tl.grid.arranging = true }
        }
        onReleased: drop()
        onCanceled: drop()
        function drop() {
            if (!tl.moving) return
            var c = tl.tc, r = tl.trow
            tl.moving = false; tl.mv = Qt.point(0, 0); tl.grid.arranging = false
            scanTiles.setTile(tl.key, c, r, tl.sw, tl.sh)   // the shown size is the one kept
        }
        onWheel: function (w) { w.accepted = true }
    }

    // ---- head: title · the tile drawer's key (one-row tiles: the key at the end of the row) ----
    Text {
        id: ttl
        visible: !tl.compact
        x: T.tile.pad; y: 0
        height: tl.tight ? T.tile.head - 6 : T.tile.head
        verticalAlignment: Text.AlignVCenter
        text: tl.title.toUpperCase()
        color: T.muted
        font.family: T.font; font.pixelSize: 11; font.letterSpacing: 1.4
    }
    Item {   // opens the tile drawer: more tiles, hide this one, arrange
        id: chip
        opacity: tl.controls ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: T.tile.fadeMs } }
        visible: opacity > 0.01
        anchors.right: parent.right; anchors.rightMargin: 6
        y: tl.compact ? (tl.height - height) / 2 : 3
        width: 26; height: 24
        TilesIcon { anchors.centerIn: parent; s: 0.8; play: dm.containsMouse
                    color: dm.containsMouse || tl.grid.arrangeMode ? T.top : T.muted }
        MouseArea {
            id: dm
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            hoverEnabled: true
            onClicked: tl.grid.drawerWanted()
            onContainsMouseChanged: containsMouse
                ? shell.tip(shell.text("Tiles: hide, show, arrange"),
                            chip.mapToItem(null, chip.width / 2, chip.height).x, chip.mapToItem(null, 0, chip.height).y)
                : shell.tip("", 0, 0)
        }
    }

    // ---- content ----
    Item {
        id: body
        x: tl.padX
        y: tl.compact ? 0 : (tl.tight ? T.tile.head - 6 : T.tile.head)
        width: tl.width - x - (tl.compact ? chip.width + 12 : tl.padX)
        height: tl.height - y - (tl.compact ? 0 : (tl.tight ? 6 : T.tile.padB))
        clip: true
    }

    // ---- resize: right edge = width, bottom edge = height, the corner = both ----
    HoverHandler { id: over; enabled: tl.controls }
    Canvas {   // the corner's rounding a little thicker while the mouse is on the tile (bright while pulling)
        id: corner
        readonly property real r: T.tile.radius
        visible: over.hovered || tl.sizing
        anchors.right: parent.right; anchors.bottom: parent.bottom
        width: r + 2; height: r + 2
        property color ink: tl.sizing ? "#ffffff" : Qt.rgba(1, 1, 1, rzC.containsMouse ? 0.75 : 0.45)
        onInkChanged: requestPaint()
        onVisibleChanged: if (visible) requestPaint()
        onPaint: {
            var c = getContext("2d"); c.reset()
            c.strokeStyle = ink; c.lineWidth = 2.5; c.lineCap = "round"
            c.beginPath(); c.arc(width - r - 0.25, height - r - 0.25, r - 0.5, 0.1 * Math.PI, 0.4 * Math.PI); c.stroke()
        }
    }
    component Pull: MouseArea {   // one resize handle: pulls the width (dx), the height (dy) or both
        property bool dx: false
        property bool dy: false
        property point p0
        visible: tl.controls
        hoverEnabled: true
        onPressed: function (m) { p0 = mapToItem(null, m.x, m.y); tl.grid.arranging = true }
        onPositionChanged: function (m) {
            if (!pressed) return
            var p = mapToItem(null, m.x, m.y)
            if (dx) tl.dw = p.x - p0.x
            if (dy) tl.dh = p.y - p0.y
        }
        onReleased: {
            var w = tl.tw, h = tl.th
            tl.dw = 0; tl.dh = 0
            tl.grid.arranging = false
            scanTiles.setTile(tl.key, tl.ent.c, tl.ent.r, w, h)
        }
    }
    Pull { id: rzR; dx: true; cursorShape: Qt.SizeHorCursor
           anchors.right: parent.right; y: tl.compact ? 4 : T.tile.head; width: 8; height: parent.height - y - 18 }
    Pull { id: rzB; dy: true; cursorShape: Qt.SizeVerCursor
           anchors.bottom: parent.bottom; x: 12; height: 8; width: parent.width - x - 18 }
    Pull { id: rzC; dx: true; dy: true; cursorShape: Qt.SizeFDiagCursor
           anchors.right: parent.right; anchors.bottom: parent.bottom; width: 18; height: 18 }
}

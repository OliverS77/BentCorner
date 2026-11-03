// Paint the card back (userprofile.py). Grid always 28 × 40, free colours. Layout:
//   on top one row of tools (pen · fill · line · rectangle · filled rectangle · oval · mirror ⇆ · mirror ⇅),
//   right-aligned undo/redo (Ctrl+Z / Ctrl+Y);
//   left the canvas, right the colour wheel + brightness, the current colour large (eyedropper above) and the last 9,
//   divider, templates (2 rows), divider, „This is how your friends see you“ – bottom-aligned with the canvas.
// Right mouse button on the canvas = pick colour. Mirroring works horizontally, vertically or both; the guide lines
// appear immediately and extend beyond the card (not part of the image). Every change goes out as edited(Text),
// always in the format "v3;28x40;c1;<Farben>;<Zeichen>" (the back's own palette, only used colours).
import QtQuick
import QtQuick.Shapes

Item {
    id: root
    property string back: ""
    property var presets: []          // [{key, name, data}]
    signal edited(string back)
    readonly property string digits: "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

    // ---------- State ----------
    property int gw: 28
    property int gh: 40
    property int corner: 1
    property string cells: ""
    property var cols: ["#000000"]    // palette of this card back (characters in cells point into it)
    property string preview: ""       // while painting or dragging a line/rectangle/oval
    property string color: "#fff1e8" // chosen colour (shown large)
    // the 9 most recently chosen colours – fixed in place; only a NEW colour shifts the row on
    property var recent: ["#ededed", "#1b1b1e", "#8a8a8e", "#e34948", "#eb6834", "#eda100", "#1baf7a", "#2a78d6", "#6250d6"]
    property real hue: 0
    property real sat: 0
    property real val: 1
    property string tool: "pen"
    property bool picking: false      // eyedropper active (a click on the canvas picks the colour)
    property bool mirrorX: false      // left = right
    property bool mirrorY: false      // top = bottom
    property var undoStack: []
    property var redoStack: []
    readonly property real cell: 11

    function hex(c) { return Qt.rgba(c.r, c.g, c.b, 1).toString().toLowerCase() }
    function setHsvFrom(c) { var q = Qt.color(c); hue = Math.max(0, q.hsvHue); sat = q.hsvSaturation; val = q.hsvValue }
    function choose(c) {   // pick colour (eyedropper): if new, it joins the front of „recent“ – old ones stay put
        c = hex(Qt.color(c))
        if (root.recent.indexOf(c) < 0) root.recent = [c].concat(root.recent).slice(0, 9)
        root.color = c
        setHsvFrom(c)
    }
    function load(b) {
        var d
        if (b && b.indexOf("v3;") === 0) {
            var p = b.split(";"), wh = p[1].split("x")
            d = {w: parseInt(wh[0]), h: parseInt(wh[1]), c: parseInt(p[2].substring(1)), cells: p.slice(4).join(""),
                 cols: p[3].split(",").map(function (x) { return "#" + x })}
        } else d = {w: 28, h: 40, c: 1, cells: "", cols: ["#000000"]}
        if (d.cells.length !== d.w * d.h) { d.cells = ""; for (var i = 0; i < d.w * d.h; i++) d.cells += "0" }
        gw = d.w; gh = d.h; corner = d.c; cols = d.cols; cells = d.cells; preview = ""
        cv.requestPaint()
    }
    property string loaded: ""
    onBackChanged: if (back !== loaded) { loaded = back; load(back) }
    Component.onCompleted: { loaded = back; load(back); setHsvFrom(color) }
    function encoded() {   // keep only used colours, renumber the characters
        var used = {}, order = [], out = ""
        for (var i = 0; i < cells.length; i++) if (!(cells[i] in used)) { used[cells[i]] = digits[order.length]; order.push(cells[i]) }
        for (var j = 0; j < cells.length; j++) out += used[cells[j]]
        var pal = order.map(function (ch) { return (cols[digits.indexOf(ch)] || "#000000").substring(1) })
        return "v3;" + gw + "x" + gh + ";c" + corner + ";" + pal.join(",") + ";" + out
    }
    property string shown: ""         // what the small preview shows (only refreshed after finished strokes)
    function code(c) {   // character for a colour (new colours go into the palette, at most 62)
        var i = cols.indexOf(c)
        if (i >= 0) return digits[i]
        if (cols.length >= digits.length) {   // full: take the most similar existing one
            var q = Qt.color(c), best = 0, bd = 1e9
            for (var k = 0; k < cols.length; k++) { var o = Qt.color(cols[k])
                var dd = Math.pow(o.r - q.r, 2) * 2 + Math.pow(o.g - q.g, 2) * 4 + Math.pow(o.b - q.b, 2) * 3
                if (dd < bd) { bd = dd; best = k } }
            return digits[best]
        }
        var n = cols.slice(); n.push(c); cols = n
        return digits[n.length - 1]
    }
    function commit(next) {   // new state: onto the undo stack, then report
        if (next === cells) return
        var u = undoStack.slice(); u.push(encoded()); if (u.length > 60) u.shift()
        undoStack = u; redoStack = []
        cells = next
        loaded = encoded(); shown = loaded; edited(loaded)
        cv.requestPaint()
    }
    function undo() {
        if (!undoStack.length) return
        var u = undoStack.slice(), prev = u.pop(), r = redoStack.slice(); r.push(encoded())
        undoStack = u; redoStack = r; load(prev); loaded = prev; shown = prev; edited(prev)
    }
    function redo() {
        if (!redoStack.length) return
        var r = redoStack.slice(), nxt = r.pop(), u = undoStack.slice(); u.push(encoded())
        undoStack = u; redoStack = r; load(nxt); loaded = nxt; shown = nxt; edited(nxt)
    }

    // ---------- Painting ----------
    function put(arr, x, y, ch) {   // one pixel – also mirrored on the chosen axes
        if (x < 0 || y < 0 || x >= gw || y >= gh) return
        var mx = gw - 1 - x, my = gh - 1 - y
        arr[y * gw + x] = ch
        if (mirrorX) arr[y * gw + mx] = ch
        if (mirrorY) arr[my * gw + x] = ch
        if (mirrorX && mirrorY) arr[my * gw + mx] = ch
    }
    function line(arr, x0, y0, x1, y1, fn) {   // Bresenham
        var dx = Math.abs(x1 - x0), dy = -Math.abs(y1 - y0), sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1, e = dx + dy
        while (true) {
            fn(arr, x0, y0)
            if (x0 === x1 && y0 === y1) break
            var e2 = 2 * e
            if (e2 >= dy) { e += dy; x0 += sx }
            if (e2 <= dx) { e += dx; y0 += sy }
        }
    }
    function shape(x0, y0, x1, y1) {   // line / rectangle / oval as preview text
        var arr = cells.split(""), c = code(color)
        var dot = function (a, x, y) { put(a, x, y, c) }
        if (tool === "line") line(arr, x0, y0, x1, y1, dot)
        else if (tool === "rect" || tool === "rectFill") {
            var ax = Math.min(x0, x1), bx = Math.max(x0, x1), ay = Math.min(y0, y1), by = Math.max(y0, y1)
            for (var y = ay; y <= by; y++) for (var x = ax; x <= bx; x++)
                if (tool === "rectFill" || x === ax || x === bx || y === ay || y === by) dot(arr, x, y)
        } else if (tool === "ellipse") {
            var cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, rx = Math.abs(x1 - x0) / 2 + 0.5, ry = Math.abs(y1 - y0) / 2 + 0.5
            for (var yy = Math.min(y0, y1); yy <= Math.max(y0, y1); yy++)
                for (var xx = Math.min(x0, x1); xx <= Math.max(x0, x1); xx++) {
                    var v = Math.pow((xx - cx) / rx, 2) + Math.pow((yy - cy) / ry, 2)
                    var vin = Math.pow((xx - cx) / Math.max(0.5, rx - 1), 2) + Math.pow((yy - cy) / Math.max(0.5, ry - 1), 2)
                    if (v <= 1 && vin > 1) dot(arr, xx, yy)
                }
        }
        return arr.join("")
    }
    function fill(x, y) {   // fill: contiguous area of the same colour (mirrored: also at the mirror positions)
        var arr = cells.split(""), to = code(color)
        var starts = [[x, y]]
        if (mirrorX) starts.push([gw - 1 - x, y])
        if (mirrorY) starts.push([x, gh - 1 - y])
        if (mirrorX && mirrorY) starts.push([gw - 1 - x, gh - 1 - y])
        for (var s = 0; s < starts.length; s++) {
            var from = arr[starts[s][1] * gw + starts[s][0]]
            if (from === to) continue
            var stack = [starts[s]]
            while (stack.length) {
                var q = stack.pop(), px = q[0], py = q[1]
                if (px < 0 || py < 0 || px >= gw || py >= gh || arr[py * gw + px] !== from) continue
                arr[py * gw + px] = to
                stack.push([px + 1, py], [px - 1, py], [px, py + 1], [px, py - 1])
            }
        }
        commit(arr.join(""))
    }

    implicitWidth: frame.width + 28 + side.width
    implicitHeight: frame.y + frame.height + 10

    // ---------- Toolbar: brushes on the left, undo/redo on the right (arranged differently) ----------
    Row {
        id: tools
        spacing: 6
        Repeater {
            model: [{"k": "pen", "g": "pen", "tip": shell.text("Pen")}, {"k": "fill", "g": "bucket", "tip": shell.text("Fill")},
                    {"k": "line", "g": "line", "tip": shell.text("Line")}, {"k": "rect", "g": "rect", "tip": shell.text("Rectangle")},
                    {"k": "rectFill", "g": "rectFill", "tip": shell.text("Filled rectangle")}, {"k": "ellipse", "g": "ellipse", "tip": shell.text("Oval")}]
            Btn { required property var modelData
                  width: 44; height: 42; glyph: modelData.g; tip: modelData.tip; led: true
                  active: root.tool === modelData.k && !root.picking
                  onClicked: { root.picking = false; root.tool = modelData.k } }
        }
        Item { width: 8; height: 1 }
        Btn { width: 44; height: 42; glyph: "butterflyX"; led: true; active: root.mirrorX
              tip: shell.text("Mirror: paint left and right the same"); onClicked: root.mirrorX = !root.mirrorX }
        Btn { width: 44; height: 42; glyph: "butterflyY"; led: true; active: root.mirrorY
              tip: shell.text("Mirror: paint top and bottom the same"); onClicked: root.mirrorY = !root.mirrorY }
    }
    Row {
        anchors.right: parent.right
        spacing: 6
        Btn { width: 44; height: 42; glyph: "undo"; enabled: root.undoStack.length > 0
              tip: shell.text("Undo (Ctrl+Z)"); onClicked: root.undo() }
        Btn { width: 44; height: 42; glyph: "redo"; enabled: root.redoStack.length > 0
              tip: shell.text("Redo (Ctrl+Y)"); onClicked: root.redo() }
    }

    // ---------- Canvas ----------
    Rectangle {
        id: frame
        y: tools.height + 22
        width: cv.width + 2; height: cv.height + 2
        color: Qt.darker(T.surface, 1.4)
        Canvas {
            onAvailableChanged: if (available) requestPaint()   // preloaded pages: catch up on the first paint request
            id: cv
            x: 1; y: 1
            width: root.gw * root.cell; height: root.gh * root.cell
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            onPaint: {
                // paint equal colours of a row in one go – far fewer draw calls than pixel by pixel
                var g = getContext("2d"), src = root.preview || root.cells, cs = root.cell, w = root.gw
                g.reset()
                for (var y = 0; y < root.gh; y++) {
                    var x = 0
                    while (x < w) {
                        var ch = src[y * w + x], x1 = x + 1
                        while (x1 < w && src[y * w + x1] === ch) x1++
                        g.fillStyle = root.cols[root.digits.indexOf(ch)] || "#000"
                        g.fillRect(x * cs, y * cs, (x1 - x) * cs, cs)
                        x = x1
                    }
                }
                g.strokeStyle = "rgba(255,255,255,0.06)"; g.lineWidth = 1
                g.beginPath()
                for (var gx = 1; gx < root.gw; gx++) { g.moveTo(gx * cs + 0.5, 0); g.lineTo(gx * cs + 0.5, height) }
                for (var gy = 1; gy < root.gh; gy++) { g.moveTo(0, gy * cs + 0.5); g.lineTo(width, gy * cs + 0.5) }
                g.stroke()
            }
        }
        Rectangle {   // pixel under the mouse
            visible: ma.containsMouse && ma.hx >= 0 && ma.hx < root.gw && ma.hy >= 0 && ma.hy < root.gh
            x: 1 + ma.hx * root.cell; y: 1 + ma.hy * root.cell; width: root.cell; height: root.cell
            color: "transparent"; border.width: 2; border.color: root.picking ? T.hi : T.text
        }
        // mirror guide lines: immediately when switched on, extend beyond the card
        Rectangle { visible: root.mirrorX; x: frame.width / 2 - 1; y: -12; width: 2; height: frame.height + 24
                    color: Qt.rgba(1, 1, 1, 0.5); radius: 1 }
        Rectangle { visible: root.mirrorY; y: frame.height / 2 - 1; x: -12; height: 2; width: frame.width + 24
                    color: Qt.rgba(1, 1, 1, 0.5); radius: 1 }
        MouseArea {
            id: ma
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            cursorShape: root.picking ? Qt.PointingHandCursor : Qt.CrossCursor
            property int hx: -1
            property int hy: -1
            property int sx: -1
            property int sy: -1
            property var work: null   // pen: current stroke (as an array)
            function at(m) { hx = Math.floor((m.x - 1) / root.cell); hy = Math.floor((m.y - 1) / root.cell) }
            function inside() { return hx >= 0 && hy >= 0 && hx < root.gw && hy < root.gh }
            onPressed: function (m) {
                at(m); if (!inside()) return
                root.forceActiveFocus()
                if (m.button === Qt.RightButton || root.picking) {
                    root.choose(root.cols[root.digits.indexOf(root.cells[hy * root.gw + hx])] || "#000000")
                    root.picking = false
                    return }
                if (root.tool === "fill") { root.fill(hx, hy); return }
                sx = hx; sy = hy
                if (root.tool === "pen") {
                    work = root.cells.split("")
                    root.put(work, hx, hy, root.code(root.color))
                    root.preview = work.join(""); cv.requestPaint()
                } else { root.preview = root.shape(sx, sy, hx, hy); cv.requestPaint() }
            }
            onPositionChanged: function (m) {
                var ox = hx, oy = hy
                at(m)
                if (!(pressedButtons & Qt.LeftButton) || sx < 0) return
                if (work) {
                    if (hx === ox && hy === oy) return   // still in the same pixel: redraw nothing
                    var ch = root.code(root.color)
                    root.line(work, Math.max(0, Math.min(root.gw - 1, ox)), Math.max(0, Math.min(root.gh - 1, oy)),
                              Math.max(0, Math.min(root.gw - 1, hx)), Math.max(0, Math.min(root.gh - 1, hy)),
                              function (a, x, y) { root.put(a, x, y, ch) })
                    root.preview = work.join("")
                } else root.preview = root.shape(sx, sy, Math.max(0, Math.min(root.gw - 1, hx)), Math.max(0, Math.min(root.gh - 1, hy)))
                cv.requestPaint()
            }
            onReleased: {
                if (root.preview !== "") { var p = root.preview; root.preview = ""; root.commit(p) }
                work = null; sx = -1; sy = -1
            }
        }
    }
    Keys.onPressed: function (e) {
        if ((e.modifiers & Qt.ControlModifier) && e.key === Qt.Key_Z) { root.undo(); e.accepted = true }
        else if ((e.modifiers & Qt.ControlModifier) && e.key === Qt.Key_Y) { root.redo(); e.accepted = true }
    }

    // ---------- right: colour · templates · preview ----------
    Item {
        id: side
        x: frame.width + 28; y: frame.y
        width: 352; height: frame.height
        Column {
            width: parent.width
            spacing: 12
            Text { text: shell.text("Color"); color: T.muted; font.family: T.font; font.pixelSize: 13 }
            Row {
                spacing: 14
                Item {   // colour wheel: angle = hue (counter-clockwise from right), distance to centre = saturation
                    id: wheel
                    width: 132; height: 132
                    Shape {
                        anchors.fill: parent
                        preferredRendererType: Shape.CurveRenderer
                        ShapePath {
                            strokeColor: "transparent"
                            fillGradient: ConicalGradient {
                                centerX: wheel.width / 2; centerY: wheel.height / 2; angle: 0
                                GradientStop { position: 0.0; color: "#ff0000" }
                                GradientStop { position: 0.1667; color: "#ffff00" }
                                GradientStop { position: 0.3333; color: "#00ff00" }
                                GradientStop { position: 0.5; color: "#00ffff" }
                                GradientStop { position: 0.6667; color: "#0000ff" }
                                GradientStop { position: 0.8333; color: "#ff00ff" }
                                GradientStop { position: 1.0; color: "#ff0000" }
                            }
                            PathAngleArc { centerX: wheel.width / 2; centerY: wheel.height / 2
                                           radiusX: wheel.width / 2; radiusY: wheel.height / 2; startAngle: 0; sweepAngle: 360 }
                        }
                        ShapePath {
                            strokeColor: "transparent"
                            fillGradient: RadialGradient {
                                centerX: wheel.width / 2; centerY: wheel.height / 2; centerRadius: wheel.width / 2
                                focalX: centerX; focalY: centerY
                                GradientStop { position: 0.0; color: "#ffffffff" }
                                GradientStop { position: 1.0; color: "#00ffffff" }
                            }
                            PathAngleArc { centerX: wheel.width / 2; centerY: wheel.height / 2
                                           radiusX: wheel.width / 2; radiusY: wheel.height / 2; startAngle: 0; sweepAngle: 360 }
                        }
                    }
                    Rectangle { anchors.fill: parent; radius: width / 2; color: "black"; opacity: 1 - root.val }
                    Rectangle {
                        width: 14; height: 14; radius: 7; color: "transparent"; border.width: 2
                        border.color: root.val > 0.55 && root.sat < 0.6 ? "#000000" : "#ffffff"
                        x: wheel.width / 2 + Math.cos(root.hue * 2 * Math.PI) * root.sat * wheel.width / 2 - 7
                        y: wheel.height / 2 - Math.sin(root.hue * 2 * Math.PI) * root.sat * wheel.height / 2 - 7
                    }
                    function pick(px, py) {
                        var r = width / 2, dx = px - r, dy = py - r
                        root.hue = (Math.atan2(-dy, dx) / (2 * Math.PI) + 1) % 1
                        root.sat = Math.min(1, Math.sqrt(dx * dx + dy * dy) / r)
                        root.color = root.hex(Qt.hsva(root.hue, root.sat, root.val, 1))
                    }
                    MouseArea {
                        anchors.fill: parent; cursorShape: Qt.CrossCursor
                        property string start: ""
                        onPressed: function (m) { start = root.color; wheel.pick(m.x, m.y) }
                        onPositionChanged: function (m) { if (pressed) wheel.pick(m.x, m.y) }
                        onReleased: root.newColor(start)
                    }
                }
                Rectangle {   // brightness
                    id: vbar
                    width: 16; height: 132; radius: 6
                    gradient: Gradient {
                        GradientStop { position: 0; color: Qt.hsva(root.hue, root.sat, 1, 1) }
                        GradientStop { position: 1; color: "#000000" } }
                    border.width: 1; border.color: T.line2
                    Rectangle { x: -3; width: parent.width + 6; height: 6; radius: 3; y: (1 - root.val) * vbar.height - 3
                                color: "transparent"; border.width: 2; border.color: T.hi }
                    function pick(py) {
                        root.val = Math.max(0, Math.min(1, 1 - py / height))
                        root.color = root.hex(Qt.hsva(root.hue, root.sat, root.val, 1))
                    }
                    MouseArea {
                        anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                        property string start: ""
                        onPressed: function (m) { start = root.color; vbar.pick(m.y) }
                        onPositionChanged: function (m) { if (pressed) vbar.pick(m.y) }
                        onReleased: root.newColor(start)
                    }
                }
                Column {   // eyedropper above the large current colour
                    spacing: 8
                    Btn { width: 50; height: 42; glyph: "picker"; led: true; active: root.picking
                          tip: shell.text("Pick a color – then click the canvas (also: right mouse button)")
                          onClicked: root.picking = !root.picking }
                    Rectangle { width: 50; height: 82; radius: 8; color: root.color; border.width: 2; border.color: T.text }
                }
                Grid {   // the 9 last colours – click selects, nothing shifts
                    columns: 3; spacing: 6
                    Repeater {
                        model: root.recent
                        Rectangle {
                            required property var modelData
                            width: 26; height: 26; radius: 6; color: modelData
                            border.width: modelData === root.color ? 2 : 1; border.color: modelData === root.color ? T.text : T.line2
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                        onClicked: { root.color = modelData; root.setHsvFrom(modelData); root.picking = false } }
                        }
                    }
                }
            }
            Rectangle { width: parent.width; height: 1; color: T.line; opacity: 0.6 }
            Text { text: shell.text("Presets"); color: T.muted; font.family: T.font; font.pixelSize: 13 }
            Grid {
                columns: 8; spacing: 8
                Repeater {
                    model: root.presets
                    Rectangle {
                        required property var modelData
                        width: 34; height: 46; radius: 6; color: "transparent"
                        border.width: 1; border.color: ph.hovered ? T.text : "transparent"
                        PixelBack { anchors.centerIn: parent; back: modelData.data; h: 42 }
                        HoverHandler { id: ph; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: { var u = root.undoStack.slice(); u.push(root.encoded()); root.undoStack = u
                                                 root.load(modelData.data); root.loaded = root.encoded(); root.shown = root.loaded
                                                 root.edited(root.loaded) } }
                    }
                }
            }
        }
        Rectangle { anchors.bottom: friends.top; anchors.bottomMargin: 14; width: parent.width; height: 1; color: T.line; opacity: 0.6 }
        Row {   // bottom-aligned with the canvas
            id: friends
            anchors.bottom: parent.bottom
            spacing: 14
            PixelBack { back: root.shown || root.loaded; h: 96 }
            Text { anchors.bottom: parent.bottom; text: shell.text("This is how\nfriends see you.")
                   color: T.dim; font.family: T.font; font.pixelSize: 12 }
        }
    }
    function newColor(prev) {   // colour finished on the wheel/slider: the previous one moves into „recent“
        var c = root.color
        if (!prev || prev === c) return
        if (root.recent.indexOf(c) < 0) root.recent = [c].concat(root.recent).slice(0, 9)
    }
}

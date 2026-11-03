// Navigation pictograms (like libview.paint_nav_icon): one stroke width, round caps, 18 px grid.
// More glyphs for buttons: "bars" (set progress), "share", "sliders" (= settings).
import QtQuick

Canvas {
    id: c
    property string key
    property color color: "#ededed"
    property real s: 1.0
    implicitWidth: 22 * s
    implicitHeight: 22 * s
    renderStrategy: Canvas.Cooperative
    onKeyChanged: requestPaint()
    onColorChanged: requestPaint()
    onSChanged: requestPaint()
    onWidthChanged: requestPaint()
    // preloaded (invisible) pages: the first paint request is lost while the surface is not ready
    onAvailableChanged: if (available) requestPaint()
    onVisibleChanged: if (visible) requestPaint()
    // mini animation on hover: play = on; t runs once 0 → 1, then everything stands still again.
    // kick() = the click: the same motion a bit bigger and slower (Orbit: one lap of the planet instead of the pulse)
    property bool play: false
    property real t: 1
    property bool clicked: false       // the running motion is a click (bigger) – else hover
    readonly property real amp: clicked ? 1.7 : 1
    onPlayChanged: if (play && !clicked && (typeof shell === "undefined" || shell.animate)) motion.restart()   // (first start: no shell)
    onTChanged: requestPaint()
    function kick() {
        if (typeof shell !== "undefined" && !shell.animate) return
        clicked = true
        motion.restart()
    }
    NumberAnimation { id: motion; target: c; property: "t"; from: 0; to: 1; duration: c.clicked ? 780 : 560; easing.type: Easing.Linear
                      onFinished: c.clicked = false }

    onPaint: {
        var g = getContext("2d")
        g.reset()
        g.translate(width / 2, height / 2)
        g.scale(s, s)
        g.strokeStyle = color
        g.fillStyle = color
        g.lineWidth = 1.9
        g.lineCap = "round"
        g.lineJoin = "round"
        function line(x1, y1, x2, y2) { g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke() }
        function poly(pts, close) {
            g.beginPath(); g.moveTo(pts[0][0], pts[0][1])
            for (var i = 1; i < pts.length; i++) g.lineTo(pts[i][0], pts[i][1])
            if (close) g.closePath()
            g.stroke()
        }
        function rrect(x, y, w, h, r, fill) {
            g.beginPath()
            g.moveTo(x + r, y); g.lineTo(x + w - r, y); g.arcTo(x + w, y, x + w, y + r, r)
            g.lineTo(x + w, y + h - r); g.arcTo(x + w, y + h, x + w - r, y + h, r)
            g.lineTo(x + r, y + h); g.arcTo(x, y + h, x, y + h - r, r)
            g.lineTo(x, y + r); g.arcTo(x, y, x + r, y, r)
            g.closePath()
            if (fill) g.fill(); else g.stroke()
        }
        function dot(x, y, r) { g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill() }
        var k = key === "sliders" ? "settings" : key
        var b = amp * Math.sin(Math.PI * Math.max(0, Math.min(1, t)))   // 0 → 1 → 0: amplitude of the motion
        var e = 1 - Math.pow(1 - Math.max(0, Math.min(1, t)), 3)  // 0 → 1 (easing out)
        var w = amp * Math.sin(Math.PI * 4 * t) * (1 - t)               // swinging out (bell, pen)
        // staggered amplitude for rows (lists, menu): part i starts a little later
        function bi(i) { var u = Math.max(0, Math.min(1, t * 1.36 - i * 0.12)); return amp * Math.sin(Math.PI * u) }
        if (k === "profile") {   // head and shoulders – nods briefly
            g.beginPath(); g.arc(0, -3.2 + 1.6 * b, 3.6, 0, Math.PI * 2); g.stroke()
            g.beginPath(); g.moveTo(-7, 8); g.bezierCurveTo(-7, 2.2, 7, 2.2, 7, 8); g.stroke()
        } else if (k === "friends") {   // two heads (front full, back offset) – clearly different from the profile
            g.beginPath(); g.arc(-2.6, -2.6, 3, 0, Math.PI * 2); g.fill()
            g.beginPath(); g.moveTo(-8.6, 8); g.bezierCurveTo(-8.6, 3, 3.4, 3, 3.4, 8); g.closePath(); g.fill()
            g.beginPath(); g.arc(4.6 + 0.8 * b, -4.2 - 2.2 * b, 2.6, 0, Math.PI * 2); g.stroke()   // the friend hops
            g.beginPath(); g.moveTo(5.6, 1.4); g.bezierCurveTo(8, 1.6, 9, 3.6, 9, 6); g.stroke()
        } else if (k === "stats") {
            // bars grow up again one after another
            var gr = function (i) { return Math.max(0, Math.min(1, e * 1.6 - i * 0.3)) }
            line(-5.5, 7.5, -5.5, 7.5 - 5 * gr(0)); line(0, 7.5, 0, 7.5 - 9 * gr(1)); line(5.5, 7.5, 5.5, 7.5 - 13 * gr(2))
        } else if (k === "sessions") {   // Logs & stats (Oliver, 29.10.: I2a – logs and stats in one): a bar chart
            // of three columns on one base line; the first, highest is the log – three entries stacked. Hover: the
            // columns grow one after another and the top entry settles on the stack; a click does it a bit bigger
            var cw = 4.2, cg = 2.6, cx0 = -(3 * cw + 2 * cg) / 2, base = 8.6, H = 17.2, sg = 1.5
            var grow = function (j) { return Math.max(0.3, Math.min(1, e * 1.7 - j * 0.28)) }
            var sh = (H - 2 * sg) / 3
            for (var si = 0; si < 3; si++) {
                var lift = si === 2 ? 1.6 * b : 0             // the newest entry lifts and settles
                var sy = base - (si + 1) * sh - si * sg - lift
                rrect(cx0, sy + sh * (1 - grow(0)), cw, sh * grow(0), Math.min(1.2, sh * grow(0) / 2), true)
            }
            ;[[7, 1], [11.5, 2]].forEach(function (col) {
                var h = col[0] * grow(col[1])
                rrect(cx0 + col[1] * (cw + cg), base - h, cw, h, Math.min(1.4, h / 2), true)
            })
        } else if (k === "scan") {   // corners contract (focus), the dot flashes
            var f = 1 - 0.2 * b
            ;[[-1, -1], [-1, 1], [1, -1], [1, 1]].forEach(function (q) {
                poly([[q[0] * 8 * f, q[1] * 3.5 * f], [q[0] * 8 * f, q[1] * 8 * f], [q[0] * 3.5 * f, q[1] * 8 * f]], false)
            })
            dot(0, 0, 2.2 + 1.2 * b)
        } else if (k === "library") {
            var sp = 1 + 0.16 * b   // cards move apart briefly
            ;[-4.3, 4.3].forEach(function (x) { [-4.6, 4.6].forEach(function (y) { rrect(x * sp - 3.1, y * sp - 3.9, 6.2, 7.8, 1.2) }) })
        } else if (k === "decks") {   // flipping through the stack: the front card slides out to the left and back
            ;[2.6, 5.2].forEach(function (d) {   // the cards behind stay put (everything within the 22 px of the icon)
                poly([[-7.5 + d, -4.5], [-7.5 + d, -4.5 - d], [3 + d, -4.5 - d], [3 + d, 8 - d], [3, 8 - d]], false)
            })
            var sl = -2.4 * b
            g.save(); g.translate(sl, 0.6 * b)
            rrect(-7.5, -4.5, 10.5, 12.5, 1.6)
            g.restore()
        } else if (k === "testing") {   // die rolls a quarter turn
            g.rotate(e * Math.PI / 2)
            rrect(-8, -8, 16, 16, 3.5)
            ;[[-3.6, -3.6], [3.6, 3.6], [0, 0], [3.6, -3.6], [-3.6, 3.6]].forEach(function (q) { dot(q[0], q[1], 1.45) })
        } else if (k === "import") {
            var dn = 2 * b   // arrows spring: in downwards, out upwards
            line(-3.5, -8.5 + dn, -3.5, 2 + dn); poly([[-6.5, -1 + dn], [-3.5, 2 + dn], [-0.5, -1 + dn]])
            line(3.5, 2 - dn, 3.5, -8.5 - dn); poly([[0.5, -5.5 - dn], [3.5, -8.5 - dn], [6.5, -5.5 - dn]])
            poly([[-8, 3], [-8, 8], [8, 8], [8, 3]])
        } else if (k === "orbit") {   // Orbit: filled core, one track open at the top right, the planet (°) in the gap –
            // hover: the track pulses (briefly bigger); click: the planet runs one lap round, no pulse
            dot(0, 0, 3.2)
            var pa = -Math.PI / 4 - (clicked ? Math.PI * 2 * e : 0), gap = 0.62
            var orr = 7.6 + (clicked ? 0 : 1.5 * b)
            g.beginPath(); g.arc(0, 0, orr, pa + gap, pa - gap + Math.PI * 2, false); g.stroke()
            dot(orr * Math.cos(pa), orr * Math.sin(pa), 2.0)
        } else if (k === "trade") {   // arrows push against each other
            var sh = 2.2 * b
            line(-8 + sh, -3.5, 7 + sh, -3.5); poly([[3.5 + sh, -7], [7 + sh, -3.5], [3.5 + sh, 0]])
            line(8 - sh, 3.5, -7 - sh, 3.5); poly([[-3.5 - sh, 0], [-7 - sh, 3.5], [-3.5 - sh, 7]])
        } else if (k === "settings") {
            [[-6, 2.5], [0, -3.5], [6, 1.0]].forEach(function (q, i) {   // sliders move back and forth briefly
                var my = q[1] + 3 * b * Math.sin(Math.PI * 2 * t + i * 2.1)
                line(q[0], -8, q[0], 8); rrect(q[0] - 2.6, my - 1.7, 5.2, 3.4, 1.2, true)
            })
        } else if (k === "bars") {   // bars run out again one after another
            [1.0, 0.6, 0.25].forEach(function (f, j) {
                var gw = Math.max(0.08, Math.min(1, e * 1.6 - j * 0.3))
                rrect(-9, -7 + j * 5.6, Math.max(2.6, 18 * f * gw), 2.6, 1.3, true)
            })
        } else if (k === "share") {   // arrow lifts off briefly
            poly([[-4, -3], [-7, -3], [-7, 8], [7, 8], [7, -3], [4, -3]])
            var up = -2.4 * b
            line(0, 3 + up, 0, -9 + up); poly([[-4, -5 + up], [0, -9 + up], [4, -5 + up]])
        } else if (k === "pin" || k === "pinOn") {   // pin: thin needle, ball on top, slightly tilted – pricks briefly
            g.save(); g.rotate(35 * Math.PI / 180); g.translate(0, 2 * b)
            g.lineWidth = 1.4; line(0, -1.5, 0, 9)
            dot(0, -5.6, 4.2)
            if (k === "pinOn") { g.fillStyle = Qt.rgba(1, 1, 1, 0.75); dot(-1.3, -6.9, 1.1) }
            g.restore()
        } else if (k === "book" || k === "bookEmpty") {   // open book (empty: crossed out)
            g.lineWidth = 1.5
            if (k === "bookEmpty") line(-10, 9, 10, -9)
            ;[-1, 1].forEach(function (sd) {
                g.beginPath(); g.moveTo(0, -5); g.quadraticCurveTo(sd * 4, -7.5, sd * 9, -6.5); g.lineTo(sd * 9, 6.5)
                g.quadraticCurveTo(sd * 4, 5.5, 0, 7.5); g.stroke()
                line(sd * 2.6, -2.6, sd * 6.6, -3.2); line(sd * 2.6, 0.4, sd * 6.6, -0.2)
            })
            line(0, -5, 0, 7.5)
        } else if (k === "star" || k === "starOn") {   // sparkles: grows briefly and turns back and forth
            g.lineWidth = 1.5
            g.translate(0, 0.5); g.rotate(0.3 * b * Math.sin(Math.PI * 2 * t)); g.scale(1 + 0.2 * b, 1 + 0.2 * b); g.translate(0, -0.5)
            g.beginPath()
            for (var q = 0; q < 10; q++) {
                var rr = q % 2 === 0 ? 8 : 3.4, ang = q * Math.PI / 5
                var px = rr * Math.sin(ang), py = 0.5 - rr * Math.cos(ang)
                if (q === 0) g.moveTo(px, py); else g.lineTo(px, py)
            }
            g.closePath()
            if (k === "starOn") g.fill(); else g.stroke()
        } else if (k === "trash") {   // trash can: lid with handle, bin slightly conical, two grooves – lid flips open
            g.lineWidth = 1.5
            g.save(); g.translate(-8, -5); g.rotate(-0.32 * b); g.translate(8, 5 - 1.6 * b)
            line(-8, -5, 8, -5)
            poly([[-2.5, -5], [-2.5, -7.5], [2.5, -7.5], [2.5, -5]])
            g.restore()
            poly([[-6, -5], [-5, 8], [5, 8], [6, -5]])
            line(-2, -2, -1.6, 5); line(2, -2, 1.6, 5)
        } else if (k === "bookmark") {   // own list: bookmark ribbon – the notch pulls up briefly
            g.lineWidth = 1.5
            poly([[-5, -8], [5, -8], [5, 8], [0, 3.5 - 2.5 * b], [-5, 8]], true)
        } else if (k === "bell") {   // bell, as plain as the pin: dome, rim, clapper – rings
            g.lineWidth = 1.5
            g.translate(0, -8.5); g.rotate(0.32 * w); g.translate(0, 8.5)
            g.beginPath(); g.moveTo(-6, 4.5); g.lineTo(-6, -0.5); g.quadraticCurveTo(-6, -6.5, 0, -6.5)
            g.quadraticCurveTo(6, -6.5, 6, -0.5); g.lineTo(6, 4.5); g.stroke()
            line(-8, 4.5, 8, 4.5)
            line(0, -6.5, 0, -8.5)
            dot(-1.8 * w, 7.3, 1.6)   // the clapper swings after it
        } else if (k === "swap") {   // ⇄ – arrows push against each other (like „trade“)
            var sw = 2.2 * b
            line(-8 + sw, -3.5, 7 + sw, -3.5); poly([[3.5 + sw, -7], [7 + sw, -3.5], [3.5 + sw, 0]])
            line(8 - sw, 3.5, -7 - sw, 3.5); poly([[-3.5 - sw, 0], [-7 - sw, 3.5], [-3.5 - sw, 7]])
        } else if (k === "menu") {   // ☰ – lines shift briefly to the right one after another
            line(-7 + 2 * bi(0), -5, 7 + 2 * bi(0), -5); line(-7 + 2 * bi(1), 0, 7 + 2 * bi(1), 0)
            line(-7 + 2 * bi(2), 5, 7 + 2 * bi(2), 5)
        } else if (k === "lists") {   // lists: dot + line, three times – lines grow one after another
            dot(-6, -5, 1.4); dot(-6, 0, 1.4); dot(-6, 5, 1.4)
            line(-2, -5, 7 + 1.6 * bi(0), -5); line(-2, 0, 7 + 1.6 * bi(1), 0); line(-2, 5, 5 + 1.6 * bi(2), 5)
        } else if (k === "close") {   // ✕ – quarter turn
            g.rotate(e * Math.PI / 2)
            line(-6, -6, 6, 6); line(6, -6, -6, 6)
        } else if (k === "sort") {   // sort: arrow up, arrow down – both twitch in their direction
            var so = 1.8 * b
            line(-3.5, 7 - so, -3.5, -7 - so); poly([[-7, -3.5 - so], [-3.5, -7 - so], [0, -3.5 - so]])
            line(3.5, -7 + so, 3.5, 7 + so); poly([[0, 3.5 + so], [3.5, 7 + so], [7, 3.5 + so]])
        } else if (k === "plus") {   // quarter turn
            g.rotate(e * Math.PI / 2)
            line(0, -6.5, 0, 6.5); line(-6.5, 0, 6.5, 0)
        } else if (k === "folderPlus") {   // folder with plus – the plus turns and grows briefly
            poly([[-8, -5.5], [-3, -5.5], [-1.5, -3.5], [8, -3.5], [8, 6.5], [-8, 6.5]], true)
            g.save(); g.translate(0, 2); g.rotate(e * Math.PI / 2); g.scale(1 + 0.3 * b, 1 + 0.3 * b)
            line(0, -2.5, 0, 2.5); line(-2.5, 0, 2.5, 0); g.restore()
        } else if (k === "play") {   // ▶ as outline – nudges forward
            g.translate(1.8 * b, 0)
            poly([[-4.5, -7], [7, 0], [-4.5, 7]], true)
        } else if (k === "pause") {   // lines move together briefly
            line(-3.5 + 1.2 * b, -6.5, -3.5 + 1.2 * b, 6.5); line(3.5 - 1.2 * b, -6.5, 3.5 - 1.2 * b, 6.5)
        } else if (k === "camera" || k === "cameraOff") {   // camera: body + lens – shutter flashes
            rrect(-8.5, -5.5, 13, 11, 2.5, false)
            poly([[4.5, -2.5], [8.5, -5], [8.5, 5], [4.5, 2.5]], true)
            if (b > 0.02 && k === "camera") dot(-2, 0, 2.6 * b)
            if (k === "cameraOff") line(-9, 8, 9, -8)
        } else if (k === "camTune" || k === "sessionTune") {   // settings: base symbol + gear at the bottom right
            g.save(); g.translate(-2, -1.5); g.scale(0.82, 0.82)
            if (k === "camTune") {   // camera (like „camera“)
                rrect(-8.5, -5.5, 13, 11, 2.5, false)
                poly([[4.5, -2.5], [8.5, -5], [8.5, 5], [4.5, 2.5]], true)
            } else {                 // pack with jagged ends (like „sessions“)
                var zp = [[-6.5, -5.5]], zi
                for (zi = 0; zi < 3; zi++) { zp.push([-6.5 + 13 / 3 * zi + 13 / 6, -8.6]); zp.push([-6.5 + 13 / 3 * (zi + 1), -5.5]) }
                zp.push([6.5, 5.5])
                for (zi = 0; zi < 3; zi++) { zp.push([6.5 - 13 / 3 * zi - 13 / 6, 8.6]); zp.push([6.5 - 13 / 3 * (zi + 1), 5.5]) }
                poly(zp, true)
            }
            g.restore()
            // gear: first clear space (the symbol below does not cut it), then ring + teeth + hub
            var gx = 5.6, gy = 5.4
            g.save(); g.globalCompositeOperation = "destination-out"
            g.beginPath(); g.arc(gx, gy, 6.6, 0, Math.PI * 2); g.fill(); g.restore()
            g.lineWidth = 1.6
            g.beginPath(); g.arc(gx, gy, 3.3, 0, Math.PI * 2); g.stroke()
            g.lineWidth = 2.1
            for (var gt = 0; gt < 8; gt++) {   // the gear turns on by one tooth
                var ga = gt * Math.PI / 4 + e * Math.PI / 4
                line(gx + Math.cos(ga) * 3.6, gy + Math.sin(ga) * 3.6, gx + Math.cos(ga) * 5.4, gy + Math.sin(ga) * 5.4)
            }
            g.lineWidth = 1.9
        } else if (k === "search") {   // magnifier – moves in a small circle (searching)
            g.translate(1.6 * Math.sin(Math.PI * 2 * t) * b, -1.6 * (1 - Math.cos(Math.PI * 2 * t)) * 0.5 * b)
            g.beginPath(); g.arc(-1.8, -1.8, 5.2, 0, Math.PI * 2); g.stroke()
            line(2.2, 2.2, 7, 7)
        } else if (k === "frame") {   // scan frame: four corners around a small card – corners focus
            g.save(); g.scale(1 - 0.16 * b, 1 - 0.16 * b)
            line(-8, -5, -8, -8); line(-8, -8, -5, -8); line(5, -8, 8, -8); line(8, -8, 8, -5)
            line(8, 5, 8, 8); line(8, 8, 5, 8); line(-5, 8, -8, 8); line(-8, 8, -8, 5)
            g.restore()
            g.lineWidth = 1.5; rrect(-3, -4.2, 6, 8.4, 1.2, false); g.lineWidth = 1.9
        } else if (k === "pen") {   // pen, tilted – scribbles briefly around the tip
            g.translate(-6.5, 7); g.rotate(0.22 * w); g.translate(6.5, -7)
            poly([[-6, 7], [-7, 3], [4, -8], [8, -4], [-3, 7]], true); line(2, -6, 6, -2)
        } else if (k === "bucket") {   // paint bucket, a drop runs out
            poly([[-7, -1], [0, -8], [6, -2], [-1, 5]], true); line(-7, -1, 6, -2)
            g.beginPath(); g.moveTo(7, 2); g.quadraticCurveTo(9, 6, 7, 7); g.quadraticCurveTo(5, 6, 7, 2); g.fill()
        } else if (k === "line") {
            line(-7, 7, 7, -7); dot(-7, 7, 1.6); dot(7, -7, 1.6)
        } else if (k === "rect") {
            rrect(-7, -6, 14, 12, 1.5, false)
        } else if (k === "rectFill") {
            rrect(-7, -6, 14, 12, 1.5, true)
        } else if (k === "ellipse") {
            g.beginPath(); g.ellipse(-7.5, -6, 15, 12); g.stroke()
        } else if (k === "darken" || k === "lighten") {   // circle, half filled (dark: right, light: left)
            g.beginPath(); g.arc(0, 0, 7, 0, Math.PI * 2); g.stroke()
            g.beginPath(); g.arc(0, 0, 7, k === "darken" ? -Math.PI / 2 : Math.PI / 2,
                                 k === "darken" ? Math.PI / 2 : Math.PI * 1.5); g.fill()
        } else if (k === "picker") {   // eyedropper: rubber bulb top right, ring, glass tube, drop at the tip
            g.beginPath(); g.arc(5, -5, 3, 0, Math.PI * 2); g.fill()
            line(1.5, -4.5, 4.5, -1.5)
            g.lineWidth = 3.2; line(-4.6, 4.6, 2.2, -2.2); g.lineWidth = 1.9
            g.translate(0, 1.6 * b)   // the drop falls briefly
            g.beginPath(); g.moveTo(-7.4, 5.4); g.quadraticCurveTo(-9.6, 8.6, -7.4, 9.2); g.quadraticCurveTo(-5.2, 8.6, -7.4, 5.4); g.fill()
        } else if (k === "butterflyX" || k === "butterflyY") {   // mirror: butterfly (left = right or top = bottom)
            g.save(); if (k === "butterflyY") g.rotate(Math.PI / 2)
            g.scale(1.15 * (1 - 0.45 * b), 1.15)                     // small it looks too dainty; flaps its wings
            line(0, -3.5, 0, 5.5)                                   // body = mirror axis
            g.lineWidth = 1.5; line(0, -3.5, -2, -6.8); line(0, -3.5, 2, -6.8); g.lineWidth = 1.9   // antennae
            for (var sd = -1; sd <= 1; sd += 2) {
                g.beginPath(); g.moveTo(sd * 2, -1.5); g.quadraticCurveTo(sd * 9.5, -8.5, sd * 8.6, -0.6)
                g.quadraticCurveTo(sd * 6, 0.8, sd * 2, -0.4); g.closePath(); g.fill()      // forewings
                g.beginPath(); g.moveTo(sd * 2, 1.2); g.quadraticCurveTo(sd * 7.8, 1.6, sd * 5.6, 7)
                g.quadraticCurveTo(sd * 3.2, 7.6, sd * 2, 1.2); g.closePath(); g.fill()     // hindwings
            }
            g.restore()
        } else if (k === "mirror") {   // mirror axis with two triangles
            line(0, -8, 0, -5); line(0, -2, 0, 1); line(0, 4, 0, 7)
            poly([[-2.5, -5], [-8, 5], [-2.5, 5]], true); poly([[2.5, -5], [8, 5], [2.5, 5]], true)
        } else if (k === "undo" || k === "redo") {   // arrow in an arc – swings out briefly in the arrow direction
            g.save(); if (k === "redo") g.scale(-1, 1)
            g.translate(1, 2); g.rotate(-0.38 * b); g.translate(-1, -2)
            g.beginPath(); g.arc(1, 2, 6, Math.PI, Math.PI * 2 + 0.6, false); g.stroke()
            poly([[-8.5, -1], [-5, 3], [-1.5, -1]])
            g.restore()
        } else if (k === "back") {   // nudges to the left
            g.translate(-2 * b, 0)
            line(7, 0, -7, 0); poly([[-2.5, -4.5], [-7, 0], [-2.5, 4.5]])
        // ---- settings sidebar, deck builder, trade: own pictograms instead of text characters ----
        } else if (k === "coins") {   // collection & prices: two coins, the top one lifts briefly
            g.beginPath(); g.ellipse(-7, 2, 14, 5); g.stroke()
            line(-7, 4.5, -7, 6.5); line(7, 4.5, 7, 6.5)
            g.beginPath(); g.moveTo(-7, 6.5); g.bezierCurveTo(-7, 9.8, 7, 9.8, 7, 6.5); g.stroke()
            g.translate(0, -2.4 * b)
            g.beginPath(); g.ellipse(-7, -6.5, 14, 5); g.stroke()
            line(-7, -4, -7, -2); line(7, -4, 7, -2)
            g.beginPath(); g.moveTo(-7, -2); g.bezierCurveTo(-7, 1.3, 7, 1.3, 7, -2); g.stroke()
        } else if (k === "tag") {   // collection & prices: price tag with a hole – swings on its string
            g.translate(-4.5, -4.5); g.rotate(0.3 * w); g.translate(4.5, 4.5)
            poly([[-8.5, -8.5], [0.5, -8.5], [8.8, -0.2], [-0.2, 8.8], [-8.5, 0.5]], true)
            g.beginPath(); g.arc(-4.5, -4.5, 1.6, 0, Math.PI * 2); g.stroke()
        } else if (k === "database") {   // card data: cylinder of three discs, the middle ring flashes
            g.beginPath(); g.ellipse(-7, -8.5, 14, 5); g.stroke()
            line(-7, -6, -7, 6); line(7, -6, 7, 6)
            g.beginPath(); g.moveTo(-7, 6); g.bezierCurveTo(-7, 9.4, 7, 9.4, 7, 6); g.stroke()
            g.globalAlpha = 0.55 + 0.45 * b
            g.beginPath(); g.moveTo(-7, 0); g.bezierCurveTo(-7, 3.4, 7, 3.4, 7, 0); g.stroke()
            g.globalAlpha = 1
        } else if (k === "display") {   // display: screen on a stand, a glint runs across
            rrect(-8.5, -7.5, 17, 11.5, 2)
            line(0, 4, 0, 7); line(-4, 7.5, 4, 7.5)
            if (b > 0.02) { g.globalAlpha = b; var gl = -7 + 12 * e; line(gl, -5.5, gl + 3, -1.5); g.globalAlpha = 1 }
        } else if (k === "palette") {   // skin: paint palette with three dots, turns a little
            g.rotate(0.35 * w)
            g.beginPath(); g.moveTo(2, 7.6); g.bezierCurveTo(-9, 9, -10, -6, 0, -8)
            g.bezierCurveTo(9, -9, 10, 2, 5, 2.6); g.bezierCurveTo(1.5, 3, 4, 6.5, 2, 7.6); g.stroke()
            dot(-4, -2.5, 1.5); dot(0, -5, 1.5); dot(4.2, -3.6, 1.5); dot(-4.2, 2.8, 1.5)
        } else if (k === "backup") {   // backup: box with an arrow going in
            poly([[-8, -1], [-8, 7.5], [8, 7.5], [8, -1]])
            line(-8, 3, 8, 3)
            var ad = 2.4 * b
            line(0, -9 + ad, 0, 0.5 + ad); poly([[-3.4, -2.8 + ad], [0, 0.6 + ad], [3.4, -2.8 + ad]])
        } else if (k === "update") {   // updates: two arrows in a circle – turn once
            g.rotate(e * Math.PI)
            g.beginPath(); g.arc(0, 0, 7, -Math.PI * 0.95, -Math.PI * 0.2); g.stroke()
            poly([[5.4, -6.8], [5.7, -4.1], [3.0, -3.8]])
            g.beginPath(); g.arc(0, 0, 7, Math.PI * 0.05, Math.PI * 0.8); g.stroke()
            poly([[-5.4, 6.8], [-5.7, 4.1], [-3.0, 3.8]])
        } else if (k === "legal") {   // legal: scales – tip briefly
            line(0, -8, 0, 7); line(-4, 7.5, 4, 7.5)
            g.save(); g.rotate(0.16 * w)
            line(-7, -5.5, 7, -5.5)
            ;[-7, 7].forEach(function (x) {
                line(x, -5.5, x - 2.6, 0.5); line(x, -5.5, x + 2.6, 0.5)
                g.beginPath(); g.moveTo(x - 3.4, 0.5); g.quadraticCurveTo(x, 4, x + 3.4, 0.5); g.closePath(); g.stroke()
            })
            g.restore()
        } else if (k === "game") {   // game: gamepad, tilts briefly
            g.rotate(0.18 * w)
            g.beginPath(); g.moveTo(-5, -4.5); g.lineTo(5, -4.5)
            g.bezierCurveTo(9.5, -4.5, 10.5, 7, 7, 7); g.bezierCurveTo(5, 7, 4, 3.5, 2.5, 3.5); g.lineTo(-2.5, 3.5)
            g.bezierCurveTo(-4, 3.5, -5, 7, -7, 7); g.bezierCurveTo(-10.5, 7, -9.5, -4.5, -5, -4.5); g.stroke()
            line(-5.5, -1, -5.5, 1.8); line(-7, 0.4, -4, 0.4); dot(4.2, -0.6, 1.2); dot(6.2, 1.4, 1.2)
        } else if (k === "heart") {   // about: heart – beats
            g.scale(1 + 0.14 * b, 1 + 0.14 * b)
            g.beginPath(); g.moveTo(0, 7.5); g.bezierCurveTo(-11, 0, -6, -10, 0, -4)
            g.bezierCurveTo(6, -10, 11, 0, 0, 7.5); g.stroke()
        } else if (k === "ticket") {   // trade offers: ticket with notches and a perforation – wobbles
            g.rotate(0.12 * w)
            g.beginPath(); g.moveTo(-9, -5.5); g.lineTo(9, -5.5); g.lineTo(9, -2)
            g.arc(9, 0, 2, -Math.PI / 2, Math.PI / 2, true); g.lineTo(9, 5.5); g.lineTo(-9, 5.5); g.lineTo(-9, 2)
            g.arc(-9, 0, 2, Math.PI / 2, -Math.PI / 2, true); g.closePath(); g.stroke()
            g.lineWidth = 1.4; for (var tk = -4; tk <= 4; tk += 2.6) line(3, tk, 3, tk + 1.2); g.lineWidth = 1.9
        } else if (k === "binder") {   // binders: album with rings on the spine, the cover opens a little
            rrect(-6.5, -8.5, 14.5, 17, 2)
            ;[-5, 0, 5].forEach(function (y) { line(-8.8, y, -4.2, y) })
            g.globalAlpha = 0.7
            rrect(-1.5 + 1.5 * b, -4.5, 6.5, 8.5, 1.2)
            g.globalAlpha = 1
        } else if (k === "flag") {   // in other decks: flag on a pole, waves
            line(-6, -8.5, -6, 8.5)
            g.beginPath(); g.moveTo(-6, -8); g.bezierCurveTo(-1, -10.5 + 2 * w, 2, -5.5 - 2 * w, 7.5, -7.5)
            g.lineTo(7.5, 0); g.bezierCurveTo(2, 2 + 2 * w, -1, -3 - 2 * w, -6, -0.5); g.stroke()
        } else if (k === "missing") {   // missing: card outline with a cross – shakes
            g.translate(1.6 * w, 0)
            g.save(); g.setLineDash([2.6, 2.2]); rrect(-6, -8.5, 12, 17, 2); g.restore()
            line(-2.6, -2.6, 2.6, 2.6); line(2.6, -2.6, -2.6, 2.6)
        } else if (k === "upgrade") {   // upgrades: arrow up over a bar – lifts
            var up2 = -2.2 * b
            line(0, 4 + up2, 0, -8 + up2); poly([[-4.5, -3.5 + up2], [0, -8 + up2], [4.5, -3.5 + up2]])
            line(-7, 8, 7, 8)
        } else if (k === "spark") {   // suggestion: four-pointed sparkle + small one – twinkles
            var sc = 1 + 0.2 * b
            g.save(); g.scale(sc, sc)
            g.beginPath(); g.moveTo(-1.5, -9); g.quadraticCurveTo(-0.5, -2.5, 5.5, -1.5); g.quadraticCurveTo(-0.5, -0.5, -1.5, 6)
            g.quadraticCurveTo(-2.5, -0.5, -8.5, -1.5); g.quadraticCurveTo(-2.5, -2.5, -1.5, -9); g.closePath(); g.stroke()
            g.restore()
            g.globalAlpha = 0.4 + 0.6 * b; dot(6.5, 6, 1.6); g.globalAlpha = 1
        } else if (k === "group") {   // Group: a flowing sideways Sankey – one bright path, the rest dimmed; on hover
            // the bright path moves on to the next branch
            g.lineWidth = 1.5
            var lit = t < 1 ? Math.min(2, Math.floor(t * 3)) : 0
            ;[-6.5, 0, 6.5].forEach(function (yy, i) {
                g.globalAlpha = i === lit ? 1 : 0.35
                g.beginPath(); g.moveTo(-8, 0); g.bezierCurveTo(-1, 0, -1, yy, 8, yy); g.stroke()
                dot(8, yy, 1.5)
            })
            g.globalAlpha = 1
            dot(-8, 0, 2)
        }
    }
}

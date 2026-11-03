// Scalper Invaders (scalper.py): your card back is the ship. Collect boosters (+1, golden +5), shoot down
// scalpers (+1, with a „Sold out“ sign 2 hits = +2). If a scalper reaches the line above the ship: −1 of 3
// lives; boosters that fall past are simply gone. Controls – all at once: mouse left/right · A/D · ←/→
// move; left click · space · W · ↑ shoot (hold = autofire); P/Esc pause. Playfield 480 × 640, scaled
// to the width. Everything is simple images/rects from fixed pools – the loop (FrameAnimation) only moves
// numbers, a counter (tick) makes the display follow.
import QtQuick

Item {
    id: root
    property string ship: ""          // card back as an image (data: URL)
    property var sprites: ({})        // {packs: [3], gold, scalper}
    property int best: 0
    signal newBest(int score)
    implicitWidth: 480; implicitHeight: 640
    height: width * 640 / 480

    readonly property int fw: 480
    readonly property int fh: 640
    readonly property int lineY: fh - 112
    readonly property int shipY: fh - 92
    property string state_: "start"   // start · play · pause · over
    property int score: 0
    property int lives: 3
    property real t: 0
    property real spawnIn: 0.6
    property real sx: fw / 2
    property real mouseX: -1
    property real mouseAt: 0
    property real fireCd: 0
    property bool firing: false
    property real shake: 0
    property var keys: ({})
    // pools (fixed size, only the numbers change)
    property var ents: []             // {kind, img, x, y, vy, dx, phase, amp, wob, hp, sold}
    property var shots: []
    property var parts: []
    property var floats: []
    property var stars: []
    readonly property int maxEnts: 40
    readonly property int maxShots: 24
    readonly property int maxParts: 90
    readonly property int maxFloats: 8

    Component.onCompleted: {
        var s = []
        for (var i = 0; i < 60; i++) s.push({x: Math.random() * fw, y: Math.random() * fh, s: Math.random() * 1.5 + 0.4, v: Math.random() * 20 + 8})
        stars = s
    }

    function reset() { score = 0; lives = 3; t = 0; spawnIn = 0.6; ents = []; shots = []; parts = []; floats = []; state_ = "play"; area.forceActiveFocus() }
    function burst(x, y, col, n) { for (var i = 0; i < n && parts.length < maxParts; i++) { var a = Math.random() * Math.PI * 2, v = 60 + Math.random() * 160
        parts.push({x: x, y: y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: 0.5 + Math.random() * 0.3, col: col}) } }
    function float(x, y, s) { if (floats.length >= maxFloats) floats.shift(); floats.push({x: x, y: y, s: s, life: 1}) }
    function spawn() {
        if (ents.length >= maxEnts) return
        var r = Math.random(), vy = 70 + t * 1.3 + Math.random() * 40
        if (r < 0.55) {
            var gold = Math.random() < 0.04
            ents.push({kind: gold ? "gold" : "pack", img: gold ? sprites.gold : sprites.packs[Math.floor(Math.random() * 3)],
                       w: 30, h: 42, x: 30 + Math.random() * (fw - 60), y: -50, vy: Math.min(260, vy * 0.9), wob: Math.random() * 6, dx: 0})
        } else {
            var sold = t > 30 && Math.random() < 0.18
            ents.push({kind: "scalper", sold: sold, hp: sold ? 2 : 1, img: sprites.scalper, w: 48, h: 36,
                       x: 40 + Math.random() * (fw - 80), y: -50, vy: Math.min(230, vy * 0.8), phase: Math.random() * 6,
                       amp: 20 + Math.min(1, t / 150) * 40, dx: 0})
        }
        spawnIn = Math.max(0.34, 1.05 - t * 0.01) * (0.7 + Math.random() * 0.6)
    }
    function key(k) { return keys[k] === true }
    function update(dt) {
        t += dt
        var dir = ((key("right") ? 1 : 0) - (key("left") ? 1 : 0))
        if (dir) { sx += dir * 380 * dt; mouseAt = 0 }
        else if (mouseX >= 0 && Date.now() - mouseAt < 4000) sx += (mouseX - sx) * Math.min(1, dt * 14)
        sx = Math.max(24, Math.min(fw - 24, sx))
        fireCd -= dt
        if ((firing || key("fire")) && fireCd <= 0 && shots.length < maxShots) { shots.push({x: sx, y: shipY - 30}); fireCd = 0.19 }
        for (var i = 0; i < shots.length; i++) shots[i].y -= 560 * dt
        shots = shots.filter(function (s) { return s.y > -20 && !s.dead })
        spawnIn -= dt; if (spawnIn <= 0) spawn()
        for (var j = 0; j < ents.length; j++) {
            var e = ents[j]
            e.y += e.vy * dt
            e.dx = e.kind === "scalper" ? Math.sin(t * 1.6 + e.phase) * e.amp : Math.sin(t * 3 + e.wob) * 3
            var ex = e.x + e.dx, hw = e.w / 2, hh = e.h / 2
            if (e.kind === "scalper") for (var k = 0; k < shots.length; k++) {
                var s = shots[k]
                if (!s.dead && Math.abs(s.x - ex) < hw && Math.abs(s.y - e.y) < hh) {
                    s.dead = true; e.hp--; burst(s.x, s.y, "#ededed", 5)
                    if (e.hp <= 0) { e.dead = true; var pts = e.sold ? 2 : 1; score += pts; burst(ex, e.y, "#d95926", 12); float(ex, e.y, "+" + pts) }
                }
            }
            if (e.dead) continue
            if (e.y + hh >= lineY) {
                if (e.kind === "scalper") {
                    e.dead = true; lives--; shake = 10; burst(ex, lineY, "#d03b3b", 18); float(ex, lineY - 20, "−1 ♥")
                    if (lives <= 0) { state_ = "over"; if (score > best) { best = score; root.newBest(score) } }
                } else if (Math.abs(ex - sx) < hw + 20) {
                    e.dead = true; var p2 = e.kind === "gold" ? 5 : 1; score += p2
                    burst(ex, lineY, e.kind === "gold" ? "#e3c063" : "#bdbdc1", e.kind === "gold" ? 24 : 10); float(ex, lineY - 20, "+" + p2)
                } else if (e.y - hh > lineY) e.dead = true
            }
        }
        shots = shots.filter(function (s) { return !s.dead })
        ents = ents.filter(function (e) { return !e.dead })
    }

    // drawing: pass values directly to the pool elements (no bindings – 200 bindings per frame made it stutter)
    function place(rep, list, n, fn) {
        for (var i = 0; i < n; i++) {
            var it = rep.itemAt(i)
            if (!it) continue
            if (i < list.length) { fn(it, list[i]); if (!it.visible) it.visible = true }
            else if (it.visible) it.visible = false
        }
    }
    function render() {
        shaker.x = shake ? (Math.random() - 0.5) * shake : 0
        shaker.y = shake ? (Math.random() - 0.5) * shake : 0
        place(starRep, stars, 60, function (it, s) { it.x = Math.round(s.x); it.y = Math.round(s.y)
            if (it.width !== s.s) { it.width = s.s; it.height = s.s; it.opacity = 0.15 + s.s * 0.25 } })
        place(entRep, ents, maxEnts, function (it, e) {
            it.x = Math.round(e.x + e.dx - e.w / 2); it.y = Math.round(e.y - e.h / 2)
            if (it.src !== e.img) { it.src = e.img; it.width = e.w; it.height = e.h }
            var gold = e.kind === "gold", sold = e.sold === true, hurt = sold && e.hp <= 1
            if (it.gold !== gold) it.gold = gold
            if (it.sold !== sold) it.sold = sold
            if (it.hurt !== hurt) it.hurt = hurt })
        place(shotRep, shots, maxShots, function (it, s) { it.x = Math.round(s.x) - 1; it.y = Math.round(s.y) })
        place(partRep, parts, maxParts, function (it, q) { it.x = q.x; it.y = q.y; it.opacity = Math.min(1, q.life * 1.6)
            if (it.color !== q.col) it.color = q.col })
        place(floatRep, floats, maxFloats, function (it, f) { if (it.text !== f.s) it.text = f.s
            it.x = f.x - it.width / 2; it.y = f.y - 16; it.opacity = f.life })
        shipItem.x = Math.round(sx - 21)
        flame1.height = 4 + Math.random() * 6; flame2.height = 3 + Math.random() * 5
    }

    FrameAnimation {
        running: root.visible
        onTriggered: {
            var dt = Math.min(0.05, frameTime)
            var slow = root.state_ === "play" ? 1 : 0.3
            for (var i = 0; i < root.stars.length; i++) { var s = root.stars[i]; s.y += s.v * dt * slow; if (s.y > root.fh) { s.y = 0; s.x = Math.random() * root.fw } }
            if (root.state_ === "play") {
                if (Qt.application.state !== Qt.ApplicationActive) root.state_ = "pause"
                else root.update(dt)
            }
            for (var j = 0; j < root.parts.length; j++) { var p = root.parts[j]; p.x += p.vx * dt; p.y += p.vy * dt; p.vy += 300 * dt; p.life -= dt }
            root.parts = root.parts.filter(function (p) { return p.life > 0 })
            for (var k = 0; k < root.floats.length; k++) { root.floats[k].y -= 40 * dt; root.floats[k].life -= dt }
            root.floats = root.floats.filter(function (f) { return f.life > 0 })
            root.shake = Math.max(0, root.shake - dt * 30)
            root.render()
        }
    }

    // ---------- Playfield (480 × 640, scaled to the width) ----------
    Rectangle {
        id: world
        width: root.fw; height: root.fh
        scale: root.width / root.fw; transformOrigin: Item.TopLeft
        color: "#0a0a0b"; radius: 16; clip: true
        border.width: 1; border.color: T.line
        Item {
            id: shaker
            anchors.fill: parent
            Repeater { id: starRep; model: 60
                Rectangle { visible: false; width: 1; height: 1; color: "#ededed" } }
            Row {   // line above the ship
                y: root.lineY; spacing: 6
                Repeater { model: 40; Rectangle { width: 6; height: 1; color: Qt.rgba(0.93, 0.93, 0.93, 0.22) } }
            }
            Repeater { id: entRep; model: root.maxEnts
                Item {
                    visible: false
                    property string src: ""
                    property bool gold: false
                    property bool sold: false
                    property bool hurt: false
                    Image { anchors.fill: parent; source: parent.src; smooth: false; asynchronous: false }
                    Rectangle {   // glow around the golden pack
                        visible: parent.gold
                        anchors.fill: parent; anchors.margins: -6; radius: 8; z: -1
                        color: Qt.rgba(0.89, 0.75, 0.39, 0.22) }
                    Rectangle {   // „Sold out“ sign
                        visible: parent.sold
                        x: -2; y: -16; width: 54; height: 13; radius: 2
                        color: parent.hurt ? "#8e8e8e" : "#ededed"
                        Text { anchors.centerIn: parent; text: "SOLD OUT"; color: "#d03b3b"; font.family: T.font; font.pixelSize: 9; font.bold: true }
                    }
                } }
            Repeater { id: shotRep; model: root.maxShots
                Rectangle { visible: false; width: 3; height: 10; color: "#ededed" } }
            Item {   // ship + flickering engine
                id: shipItem
                visible: root.state_ !== "start"
                y: root.shipY - 30; width: 42; height: 60
                Rectangle { id: flame1; x: 15; y: 60; width: 4; height: 6; color: Qt.rgba(0.93, 0.93, 0.93, 0.55) }
                Rectangle { id: flame2; x: 23; y: 60; width: 4; height: 5; color: Qt.rgba(0.93, 0.93, 0.93, 0.55) }
                Image { anchors.fill: parent; source: root.ship; smooth: false }
            }
            Repeater { id: partRep; model: root.maxParts
                Rectangle { visible: false; width: 3; height: 3 } }
            Repeater { id: floatRep; model: root.maxFloats
                Text { visible: false; color: "#ededed"; font.family: T.font; font.pixelSize: 16; font.bold: true } }
        }
        // header: points · best · lives
        Text { x: 18; y: 12; text: ("0000" + root.score).slice(-Math.max(4, String(root.score).length))
               color: "#ededed"; font.family: T.display; font.pixelSize: 22; font.bold: true }
        Text { anchors.horizontalCenter: parent.horizontalCenter; y: 18; text: "BEST " + root.best
               color: "#686868"; font.family: T.display; font.pixelSize: 11; font.letterSpacing: 1 }
        Row { anchors.right: parent.right; anchors.rightMargin: 18; y: 14; spacing: 6
            Repeater { model: 3
                Image { required property int index; width: 14; height: 20; source: root.ship; smooth: false
                        opacity: index < root.lives ? 1 : 0.18 } } }
        // start · pause · game over
        Rectangle {
            anchors.fill: parent; visible: root.state_ !== "play"; color: Qt.rgba(0.04, 0.04, 0.045, 0.72)
            property bool blink: true
            Timer { interval: 500; repeat: true; running: parent.visible; onTriggered: parent.blink = !parent.blink }
            Column {
                visible: root.state_ === "start"; anchors.centerIn: parent; spacing: 14
                Image { anchors.horizontalCenter: parent.horizontalCenter; width: 84; height: 120; source: root.ship; smooth: false }
                Text { anchors.horizontalCenter: parent.horizontalCenter; text: "SCALPER INVADERS"
                       color: "#ededed"; font.family: T.display; font.pixelSize: 40; font.bold: true }
                Text { anchors.horizontalCenter: parent.horizontalCenter; horizontalAlignment: Text.AlignHCenter
                       text: shell.text("Collect boosters, shoot the scalpers –\ndon't let any cross the line.")
                       color: "#b5b5b5"; font.family: T.font; font.pixelSize: 14 }
                Row { anchors.horizontalCenter: parent.horizontalCenter; spacing: 30
                    Image { width: 30; height: 42; source: root.sprites.packs ? root.sprites.packs[0] : ""; smooth: false }
                    Image { width: 30; height: 42; source: root.sprites.gold || ""; smooth: false }
                    Image { width: 48; height: 36; source: root.sprites.scalper || ""; smooth: false } }
                Text { anchors.horizontalCenter: parent.horizontalCenter; opacity: parent.parent.blink ? 1 : 0
                       text: shell.text("Click or space to start"); color: "#ededed"; font.family: T.font; font.pixelSize: 14; font.bold: true }
                Text { anchors.horizontalCenter: parent.horizontalCenter; horizontalAlignment: Text.AlignHCenter
                       text: shell.text("Move: mouse · A/D · ←/→    Shoot: click · space · W · ↑")
                       color: "#686868"; font.family: T.font; font.pixelSize: 11 }
            }
            Column {
                visible: root.state_ === "pause"; anchors.centerIn: parent; spacing: 8
                Text { anchors.horizontalCenter: parent.horizontalCenter; text: shell.text("PAUSED"); color: "#ededed"; font.family: T.display; font.pixelSize: 34; font.bold: true }
                Text { anchors.horizontalCenter: parent.horizontalCenter; text: shell.text("P, click or space – continue"); color: "#b5b5b5"; font.family: T.font; font.pixelSize: 14 }
            }
            Column {
                visible: root.state_ === "over"; anchors.centerIn: parent; spacing: 6
                Text { anchors.horizontalCenter: parent.horizontalCenter; text: "SOLD OUT."; color: "#ededed"; font.family: T.display; font.pixelSize: 38; font.bold: true }
                Text { anchors.horizontalCenter: parent.horizontalCenter; text: root.score; color: "#ededed"; font.family: T.display; font.pixelSize: 64; font.bold: true }
                Text { anchors.horizontalCenter: parent.horizontalCenter; color: "#8e8e8e"; font.family: T.display; font.pixelSize: 12
                       text: root.score >= root.best && root.score > 0 ? shell.text("NEW BEST") : "BEST " + root.best }
                Item { width: 1; height: 40 }
                Text { anchors.horizontalCenter: parent.horizontalCenter; opacity: parent.parent.blink ? 1 : 0
                       text: shell.text("Click or space – again"); color: "#ededed"; font.family: T.font; font.pixelSize: 14; font.bold: true }
            }
        }
        // input
        MouseArea {
            id: area
            anchors.fill: parent
            hoverEnabled: true
            focus: true
            cursorShape: root.state_ === "play" ? Qt.BlankCursor : Qt.PointingHandCursor
            onPositionChanged: function (m) { root.mouseX = m.x; root.mouseAt = Date.now() }
            onPressed: function (m) {
                forceActiveFocus()
                if (root.state_ === "start" || root.state_ === "over") root.reset()
                else if (root.state_ === "pause") root.state_ = "play"
                else root.firing = true
            }
            onReleased: root.firing = false
            Keys.onPressed: function (e) {
                var k = e.key, fire = k === Qt.Key_Space || k === Qt.Key_W || k === Qt.Key_Up
                var left = k === Qt.Key_A || k === Qt.Key_Left, right = k === Qt.Key_D || k === Qt.Key_Right
                if (k === Qt.Key_P || k === Qt.Key_Escape) {
                    if (root.state_ === "play") { root.state_ = "pause"; e.accepted = true }
                    else if (root.state_ === "pause") { root.state_ = "play"; e.accepted = true }
                    return
                }
                if (!(fire || left || right || k === Qt.Key_Return || k === Qt.Key_Enter)) return
                e.accepted = true
                if ((fire || k === Qt.Key_Return || k === Qt.Key_Enter) && !e.isAutoRepeat && (root.state_ === "start" || root.state_ === "over")) { root.reset(); return }
                if (root.state_ === "pause" && fire) { root.state_ = "play"; return }
                var ks = root.keys
                if (fire) ks.fire = true; if (left) ks.left = true; if (right) ks.right = true
            }
            Keys.onReleased: function (e) {
                if (e.isAutoRepeat) return
                var k = e.key, ks = root.keys
                if (k === Qt.Key_Space || k === Qt.Key_W || k === Qt.Key_Up) ks.fire = false
                if (k === Qt.Key_A || k === Qt.Key_Left) ks.left = false
                if (k === Qt.Key_D || k === Qt.Key_Right) ks.right = false
            }
        }
    }
    onActiveFocusChanged: if (!activeFocus) { keys = ({}); firing = false }
}

// Button. Look „Grau“ = key from the key lab (Key.qml: „B · OP-XY knapp“ – click presses it in, release springs
// it back; hover only brightens the text; on/off is shown by the little lamp on the left, the key stays up).
// Look „Neon“ = border and text glow in the accent colour.
import QtQuick

Item {
    id: b
    property string text
    property bool active: false        // active (selected) – or checked when checkable
    property bool checkable: false
    property bool checked: false
    property bool led: checkable       // part of a selection: lamp always there (off grey, on white), space reserved
    property bool ledAlways: false     // always show the lamp, even outside the Grau look (like the nav buttons)
    property bool iconMotion: true     // icon plays a mini animation on hover (off: false)
    property bool danger: false
    property bool inverted: false      // on like a switch: bright surface, dark icon (e.g. pin)
    property bool primary: false       // primary action: raised as always, with a brighter border (not „pressed“)
    property bool compact: false
    property string glyph: ""          // icon only (NavIcon key)
    property string navIcon: ""        // icon before the text
    property url iconSource: ""        // small image before the text (e.g. the game's pixel icon), scaled crisply
    property int navLevel: 0           // 0 normal, 1 small text, 2 icon only
    property bool badge: false         // „something is ready here“
    property int badgeCount: 0         // a number instead of the dot (e.g. open requests)
    property string badgeText: ""      // a character instead of the dot (e.g. ∞ – all games)
    readonly property bool badgePill: badgeCount > 0 || badgeText !== ""
    function blinkBadge() { if (badgeLd.item) badgeLd.item.blink() }
    property int backDir: 0            // origin tab: -1 arrow left, +1 arrow right
    property real pulse: -1            // nav way back (P4): -1 = off, else the lamp's brightness 0…1 (NavStatic's clock)
    property string tip: ""
    property color alertInk: "transparent"   // warning colour for text/icon (e.g. camera off = red)
    property real fontPx: compact ? 12 : 14
    property bool marquee: false       // text too long: „…“ at rest, scrolls through on hover (e.g. selection)
    signal clicked()
    // the click plays the icon's bigger motion (hover: the small one) – a button gone after its click simply isn't seen
    onClicked: if (b.iconMotion) { if (glyphLd.item) glyphLd.item.kick(); else if (navLd.item) navLd.item.kick() }

    readonly property bool on: active || (checkable && checked)
    readonly property bool down: tap.pressed || on
    property real h: hover.hovered && enabled ? 1 : 0
    Behavior on h { NumberAnimation { duration: 170; easing.type: Easing.OutCubic } }

    // origin tab: the arrow sits where the active tab's dot would otherwise be (statusSlot)
    readonly property real ledRoom: T.gray && led && !glyph ? 16 : 0   // space for the lamp on the left
    readonly property bool statusSlot: !glyph && width - txt.implicitWidth - (navIcon ? 26 : 0) > (led ? 22 : 30)
    readonly property string label: backDir !== 0 && (statusSlot || navLevel >= 2) ? text
                                    : (backDir < 0 ? "←  " + text : (backDir > 0 ? text + "  →" : text))
    implicitWidth: glyph ? 44 : Math.max(compact ? 40 : 60, txt.implicitWidth + (navIcon ? 26 + 18 : 0)
                                          + (iconSource.toString() !== "" ? 29 : 0) + (compact ? 28 : 40) + ledRoom)
    implicitHeight: compact ? 30 : 36
    opacity: enabled ? 1 : 0.55

    readonly property real r: Math.min(height / 2, T.btnRadius * height / 34)
    readonly property color base: T.button
    readonly property color ink: !enabled ? "#5e5e5e" : alertInk.a > 0 ? alertInk : inverted ? T.onHi
                                  : !T.gray ? (on || backDir !== 0 ? "#ffffff" : Qt.tint(danger ? T.text2 : T.text, Qt.rgba(1, 1, 1, 0.25 * h)))
                                  : Qt.tint(on || backDir !== 0 || primary ? T.inkOn : T.inkOff,
                                            T.light ? Qt.rgba(0, 0, 0, h) : Qt.rgba(0.957, 0.957, 0.957, h))

    // --- Grau: key (Key.qml) ---
    Key {
        id: key
        anchors.fill: parent
        visible: T.gray
        radius: b.r
        light: b.inverted
        down: tap.pressed
    }
    // --- Neon ---
    Rectangle {
        anchors.fill: parent
        visible: !T.gray
        radius: b.r
        color: b.on && !b.danger ? T.accent_deep : (tap.pressed ? Qt.lighter(T.button, 1.35) : T.button)
        border.width: 1.2
        border.color: b.on || b.h > 0.5 ? T.accent : T.line2
        Behavior on border.color { ColorAnimation { duration: 170 } }
    }
    Rectangle {   // inverted: bright surface (Grau: bright key in Key)
        anchors.fill: parent
        visible: b.inverted && !T.gray
        radius: b.r
        color: Qt.lighter("#d9d9d9", 1 + 0.08 * b.h)
        border.width: 1; border.color: Qt.rgba(0, 0, 0, 0.86)
    }
    Rectangle {   // Neon: primary action with a bright border
        anchors.fill: parent
        visible: !T.gray && b.primary && !b.on && b.enabled
        radius: b.r
        color: "transparent"
        border.width: 1.2
        border.color: Qt.rgba(1, 1, 1, 0.42 + 0.25 * b.h)
    }
    Rectangle {   // Neon: origin tab with a bright outline
        anchors.fill: parent
        visible: !T.gray && b.backDir !== 0
        radius: b.r
        color: "transparent"
        border.width: 1.5
        border.color: "#ffffff"
    }
    // Grau: primary action / origin tab underlined instead of outlined – the line is always 15 % of the button width,
    // no matter how long the word is; it sinks with the key
    Rectangle {
        visible: T.gray && b.enabled && ((b.primary && !b.on) || b.backDir !== 0)
        width: Math.max(10, Math.round(b.width * 0.15)); height: 2; radius: 1
        x: (b.width - width) / 2; y: b.height - 7
        scale: key.scale
        color: b.backDir !== 0 ? T.hi : (T.light ? Qt.rgba(0, 0, 0, 0.55 + 0.35 * b.h) : Qt.rgba(1, 1, 1, 0.55 + 0.35 * b.h))
    }
    // lamp on the left (like on the OP-XY): off = flat grey, on = flat white – selection buttons (led) always have it
    Rectangle {
        visible: b.statusSlot && (b.on || b.pulse >= 0 || ((T.gray || b.ledAlways) && b.led)) && !(b.backDir !== 0 && !b.on)
        x: Math.min(12, b.r + 6) - 2.5; y: b.height / 2 - 2.5
        width: 5; height: 5; radius: 2.5
        scale: T.gray ? key.scale : 1
        color: b.pulse >= 0 ? Qt.tint(T.off, Qt.rgba(Qt.color(T.hi).r, Qt.color(T.hi).g, Qt.color(T.hi).b, b.pulse)) : b.on ? T.hi : T.off
        Behavior on color { enabled: b.pulse < 0; ColorAnimation { duration: 160 } }
    }
    Rectangle {   // icon-only tabs: the way-back lamp under the icon
        visible: b.pulse >= 0 && b.navLevel >= 2
        x: (b.width - 5) / 2; y: b.height - 9
        width: 5; height: 5; radius: 2.5
        color: Qt.tint(T.off, Qt.rgba(Qt.color(T.hi).r, Qt.color(T.hi).g, Qt.color(T.hi).b, b.pulse))
    }

    // icon + lamp only (switches like mirror, tool choice): dot bottom centre, icon slightly higher
    Rectangle {
        visible: b.glyph !== "" && b.led
        x: b.width / 2 - 2.5; y: b.height - 9
        width: 5; height: 5; radius: 2.5
        scale: T.gray ? key.scale : 1
        color: b.on ? T.hi : T.off
        Behavior on color { ColorAnimation { duration: 160 } }
    }
    // content
    // the parts a button rarely needs are built only when it uses them (icons are Canvas items, three per button
    // in every list row made long lists stall – review .101)
    Loader {
        id: glyphLd
        active: b.glyph !== ""
        anchors.centerIn: parent
        anchors.verticalCenterOffset: b.led ? -3 : 0
        sourceComponent: NavIcon {
            key: b.glyph; color: b.ink; s: 0.9
            play: b.iconMotion && b.enabled && hover.hovered
        }
    }
    Row {
        id: content
        visible: b.glyph === ""
        anchors.centerIn: parent
        anchors.horizontalCenterOffset: b.statusSlot && b.ledRoom > 0 ? b.ledRoom / 2 : 0
        spacing: b.navLevel === 1 ? 6 : 9
        Image {
            visible: b.iconSource.toString() !== ""
            source: b.iconSource
            width: 20; height: 20; smooth: false; mipmap: false
            anchors.verticalCenter: parent.verticalCenter
        }
        Loader {
            id: navLd
            active: b.navIcon !== ""
            visible: active
            anchors.verticalCenter: parent.verticalCenter
            sourceComponent: NavIcon {
                key: b.navIcon; color: b.ink
                play: b.iconMotion && b.enabled && hover.hovered
            }
        }
        Text {
            id: txt
            visible: (b.navLevel < 2 || b.navIcon === "") && b.label !== ""
            anchors.verticalCenter: parent.verticalCenter
            // too narrow (e.g. long selection in half a column): truncate instead of running over the edge
            width: Math.min(implicitWidth, Math.max(10, b.width - 24 - (b.navIcon !== "" ? 26 : 0)))
            elide: Text.ElideRight
            text: b.label
            color: b.marquee ? "transparent" : b.ink   // (opacity would also fade out the scrolling text inside)
            font.family: T.font
            // two words stacked (tab names like "Logs\nStats"): two small lines next to the icon, same height
            readonly property bool stacked: b.label.indexOf("\n") >= 0
            font.pixelSize: stacked ? (b.navLevel === 1 ? 10 : 11) : b.navLevel === 1 ? 12 : b.fontPx
            lineHeight: stacked ? 1.12 : 1
            font.bold: true
            Rectangle {   // stacked: a very thin line between the two words (Oliver, review .101 – a test)
                visible: txt.stacked && !b.marquee
                width: txt.width; height: 1; y: Math.round(txt.height / 2)
                color: b.ink; opacity: 0.3
            }
            Loader {
                active: b.marquee
                anchors.fill: parent
                sourceComponent: Marquee {
                    text: b.label; color: b.ink; px: txt.font.pixelSize; bold: true
                    running: hover.hovered
                }
            }
        }
    }
    Text {   // icon only + origin: small arrow next to it
        visible: b.navLevel >= 2 && b.navIcon !== "" && b.backDir !== 0
        anchors.verticalCenter: parent.verticalCenter
        x: b.backDir < 0 ? 8 : b.width - width - 8
        text: b.backDir < 0 ? "←" : "→"
        color: b.ink; font.family: T.font; font.pixelSize: 12; font.bold: true
    }
    Loader {   // origin tab: small back arrow in place of the dot
        active: b.backDir !== 0 && !b.on && b.statusSlot && b.navLevel < 2
        x: Math.min(12, b.r + 6) - width / 2; y: b.height / 2 - height / 2
        sourceComponent: NavIcon { key: "back"; color: b.ink; s: 0.55 }
    }
    Loader {   // hint dot (+ its calm ripple) – only on a button that has one
        id: badgeLd
        active: b.badge || b.badgePill
        anchors.fill: parent
        sourceComponent: Item {
            function blink() { badgeBlink.restart() }
            Rectangle {   // hint dot – with a number when something is counted (e.g. open friend requests)
                id: badgeDot
                x: b.width - width - 6 + (b.badgePill ? 4 : 0); y: b.badgePill ? 0 : 3.5
                width: b.badgePill ? Math.max(17, bc.implicitWidth + 9) : 9; height: b.badgePill ? 17 : 9
                SequentialAnimation on opacity {   // blink twice (e.g. when entering the price alarms)
                    id: badgeBlink
                    running: false
                    NumberAnimation { to: 0.15; duration: 140 } NumberAnimation { to: 1; duration: 160 }
                    NumberAnimation { to: 0.15; duration: 140 } NumberAnimation { to: 1; duration: 160 }
                }
                radius: height / 2
                color: b.badgeText !== "" ? "transparent" : "#ffa24a"   // notification: orange – unlike the white lamps
                border.width: b.badgeText !== "" ? 0 : 2; border.color: Qt.rgba(0, 0, 0, 0.8)
                Text { id: bc; anchors.centerIn: parent; visible: b.badgePill
                       text: b.badgeText !== "" ? b.badgeText : (b.badgeCount > 9 ? "9+" : b.badgeCount)
                       style: b.badgeText !== "" ? Text.Outline : Text.Normal; styleColor: Qt.rgba(0, 0, 0, 0.8)
                       color: b.badgeText !== "" ? "#ffa24a" : T.onHi; font.family: T.font
                       font.pixelSize: b.badgeText !== "" ? 17 : 10; font.bold: true }
            }

            // calm drop: every 30 s a ring spreads around the lamp – inside the button (clipped)
            Item {
                anchors.fill: parent
                clip: true
                visible: shell.animate

                Rectangle {
                    id: ripple
                    x: badgeDot.x + badgeDot.width / 2 - width / 2; y: badgeDot.y + badgeDot.height / 2 - height / 2
                    width: badgeDot.height; height: width; radius: width / 2
                    color: "transparent"; border.width: 1.5; border.color: "#ffa24a"
                    opacity: 0
                    SequentialAnimation on scale {
                        running: shell.animate
                        loops: Animation.Infinite
                        PauseAnimation { duration: 2500 }
                        NumberAnimation { from: 1; to: 3.2; duration: 1600; easing.type: Easing.OutCubic }
                        PauseAnimation { duration: 27000 }
                    }
                    SequentialAnimation on opacity {
                        running: shell.animate
                        loops: Animation.Infinite
                        PauseAnimation { duration: 2500 }
                        NumberAnimation { from: 0.7; to: 0; duration: 1600; easing.type: Easing.OutCubic }
                        PauseAnimation { duration: 27000 }
                    }
                }
            }
        }
    }

    // keyboard: Tab jumps here, Space/Enter press it (before the page's shortcuts, e.g. Space = pause)
    activeFocusOnTab: enabled && visible
    Keys.onShortcutOverride: function (e) { if (e.key === Qt.Key_Space || e.key === Qt.Key_Return || e.key === Qt.Key_Enter) e.accepted = true }
    Keys.onPressed: function (e) {
        if (e.key === Qt.Key_Space || e.key === Qt.Key_Return || e.key === Qt.Key_Enter) { e.accepted = true; b.clicked() }
    }
    Rectangle {   // focus ring (keyboard only – clicks take no focus)
        visible: b.activeFocus
        anchors.fill: parent; anchors.margins: -3
        radius: b.r + 3
        color: "transparent"; border.width: 1.5; border.color: T.hi
        opacity: 0.8
    }
    HoverHandler { id: hover; cursorShape: b.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor }
    TapHandler {
        id: tap
        enabled: b.enabled
        gesturePolicy: TapHandler.ReleaseWithinBounds   // the press is the button's alone – nothing behind it clicks
        // … and no drag handler takes it over: Qt offers a press to the handlers of every item under the mouse, a card
        // tile below a menu or dialog took it and the click was lost (review .101). Flickables may still scroll.
        grabPermissions: PointerHandler.CanTakeOverFromItems | PointerHandler.CanTakeOverFromHandlersOfDifferentType
                         | PointerHandler.ApproveTakeOverByItems | PointerHandler.ApproveTakeOverByHandlersOfSameType
        onTapped: b.clicked()   // checked always comes from outside (binding) – toggling it here would break it
    }
    // tooltip: after a short rest over the button (shown by the window so nothing is clipped)
    Timer { id: tipT; interval: 650; onTriggered: { var p = b.mapToItem(null, b.width / 2, b.height); shell.tip(b.tip, p.x, p.y) } }
    Connections {
        target: hover
        function onHoveredChanged() { if (hover.hovered && b.tip !== "") tipT.restart(); else { tipT.stop(); shell.tip("", 0, 0) } }
    }
}

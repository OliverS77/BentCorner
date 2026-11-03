// View within a page (deck overview ↔ deck, lists ↔ list editor): the old one fades out, the new one
// slides in a little (depth 1 = deeper: from below, depth 0 = overview: from above). During the switch
// each view is drawn as one image (layer) – so the crossfade costs next to nothing, even with many tiles.
import QtQuick

Item {
    id: v
    property bool shown: false
    property int depth: 1
    readonly property int dur: shell.animate ? Math.round(240 * shell.speed) : 120
    property real t: shown ? 1 : 0
    Behavior on t { NumberAnimation { duration: v.dur; easing.type: Easing.OutQuad } }
    readonly property bool moving: t > 0.002 && t < 0.998
    visible: t > 0.002
    enabled: shown
    opacity: t
    layer.enabled: moving
    layer.smooth: true
    transform: Translate { y: shell.animate ? (v.depth === 0 ? -14 : 14) * (1 - v.t) : 0 }
    // build the content only when the view appears, tear it down when fully faded out (lazy: Component) –
    // for deep views (deck editor, friend …): merely hidden, their thousands of items made every frame of the whole
    // app more expensive (Qt 6.11 walks all items of the window after every new tile). Overviews stay fixed.
    // built asynchronously (the UI keeps running while opening) and torn down after WARM_MS unused – whoever
    // is working there and briefly goes back doesn't wait the next time it opens.
    property Component lazy: null
    property bool warm: false
    readonly property int warmMs: 60000
    onShownChanged: if (shown) { cool.stop(); warm = true } else cool.restart()
    Timer { id: cool; interval: v.warmMs; onTriggered: v.warm = false }
    Loader {
        anchors.fill: parent
        active: v.lazy !== null && (v.shown || v.visible || v.warm)
        asynchronous: true
        sourceComponent: v.lazy
    }
}

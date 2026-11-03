// Bent°Corner – main window in Qt Quick. Navigation at the top (fixed bar), the pages below. Page transition:
// „flip“ (new page from behind or in front) or „slide“ (sideways), as set in Appearance.
// On the scan page the navigation only slides in when the mouse is at the top edge (grip line as a hint).
import QtQuick
import QtQuick.Window
import "components"

Window {
    id: win
    title: typeof brandInfo !== "undefined" ? brandInfo.name : ""   // ui/brand.NAME
    color: T.bg
    minimumWidth: 1120
    minimumHeight: 560
    width: 1600
    height: 900
    visible: false

    property string page: "library"
    property string prev: ""
    property int dir: 1
    property var visited: ({"library": true})
    // lazy pages (shell.lazyPages): built when opened, torn down LAZY_WARM ms after leaving them
    property var leftAt: ({})
    readonly property int lazyWarm: 60000
    Timer {
        interval: 10000; repeat: true; running: win.visible
        onTriggered: {
            var now = Date.now(), v = null
            for (var k in win.leftAt) {
                if (k !== win.page && win.visited[k] === true && now - win.leftAt[k] > win.lazyWarm) {
                    v = v || Object.assign({}, win.visited)
                    delete v[k]
                }
            }
            if (v) win.visited = v
        }
    }
    readonly property bool scanPage: page === "scan"
    // a dialog covers the window (its background is opaque): everything below is switched off. Qt offers a press to the
    // pointer handlers of every item under the mouse, covered or not – a card tile's DragHandler below took the press
    // over from the dialog's button, so the first click did nothing (Oliver, review .101: „immer zwei Klicks“)
    readonly property bool covered: sheetHost.opaque
    // Navigation: always the fixed bar (the carousel no longer exists)
    readonly property Item nav: navFixed

    onClosing: function (close) { close.accepted = shell.requestClose() }

    // ---------- Pages ----------
    Item {
        id: pages
        anchors.fill: parent
        clip: true
        enabled: !win.covered
        // every page keeps its position: the scan window reaches to the top (bar above it), all others start below the
        // bar – otherwise the leaving page would change size mid-transition (camera image jumped/scaled)

        property real u: 1.0   // page transition progress 0..1
        NumberAnimation on u { id: flip; running: false; from: 0; to: 1; duration: 480 * shell.speed
                               easing.type: Easing.InOutCubic }

        Loading {   // a page that wasn't there yet is being built: the central loading sign in its place
            anchors.horizontalCenter: parent.horizontalCenter
            y: win.nav.height + (pages.height - win.nav.height - height) / 2
            visible: win.pageBuilding && buildShow.done
            Timer { id: buildShow; property bool done: false; interval: 150
                    running: win.pageBuilding; onRunningChanged: if (running) done = false; onTriggered: done = true }
        }
        Repeater {
            model: shell.pageKeys
            delegate: Loader {
                id: ld
                required property string modelData
                readonly property bool isNew: modelData === win.page
                readonly property bool isOld: modelData === win.prev && flip.running
                width: pages.width
                y: modelData === "scan" ? 0 : win.nav.height
                height: pages.height - y
                active: win.visited[modelData] === true
                // in pieces, also the page just clicked (review .93, Oliver: a short freeze is fine, but always with
                // the loading sign): while it builds, Loading shows in the page area and keeps moving
                asynchronous: true
                readonly property bool building: isNew && active && status === Loader.Loading
                onBuildingChanged: win.pageBuilding = building
                onStatusChanged: if (status === Loader.Ready || status === Loader.Error) {
                    win.loadedCount++
                    if (isNew) win.startReady = true   // the start page is ready: the loading screen may go
                    if (isNew && win.reviving) win.revived()
                }
                visible: (isNew || isOld) && status === Loader.Ready
                z: isNew ? 2 : 1
                source: shell.pageSourceFor(modelData, shell.gameRev)
                onLoaded: {
                    if (item && item.key !== undefined) item.key = modelData
                    if (item && item.enter) item.enter()
                }

                readonly property real u: pages.u
                readonly property bool slide: shell.pageAnim === "slide"
                // Flip: forward, the new page comes from behind, the old one flies away to the front (back: reversed)
                opacity: !flip.running ? 1
                         : slide ? 1
                         : win.dir > 0 ? (isNew ? Math.min(1, u * 1.15) : 1 - Math.min(1, u * 1.25))
                                       : (isNew ? Math.min(1, u * 1.25) : 1 - Math.min(1, u * 1.15))
                scale: !flip.running || slide ? 1
                       : win.dir > 0 ? (isNew ? 0.86 + 0.14 * u : 1 + 0.14 * u)
                                     : (isNew ? 1.14 - 0.14 * u : 1 - 0.14 * u)
                transformOrigin: Item.Top
                x: !flip.running || !slide ? 0
                   : (isNew ? win.dir * (width + 28) * (1 - u) : -win.dir * (width + 28) * u)
                Rectangle {   // Slide: the leaving page dims slightly
                    anchors.fill: parent
                    visible: flip.running && ld.slide && ld.isOld
                    color: Qt.rgba(0, 0, 0, 0.27 * ld.u)
                }
            }
        }
    }

    // ---------- Navigation ----------
    // Scan page: the page is the stream (scantiles.py) – a few seconds without the mouse the bar slides away, a move
    // brings it back; it stays open as long as the games row or the download list is expanded
    // ... but not while a window of the scan page is open (card search/edit, stats, camera): nothing moves then
    readonly property bool scanAutoHide: win.scanPage && !studioView.on && !scanView.cardPanel.shown
                                         && !scanView.statsPanel.shown && !scanView.quickOpen
    onScanAutoHideChanged: if (scanAutoHide) navWake.restart()
    property real navPos: win.scanAutoHide ? (navWake.running || gamePick.open || gamePick.listOpen ? 1 : 0) : 1
    Behavior on navPos { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
    property point lastMouse: Qt.point(-1, -1)   // only real movement counts (not the bar sliding in)
    HoverHandler { id: topZone
        onPointChanged: { var p = point.scenePosition
            if (Math.abs(p.x - win.lastMouse.x) + Math.abs(p.y - win.lastMouse.y) > 2) { win.lastMouse = p; navWake.restart() } } }
    Timer { id: navWake; interval: T.tile.wakeMs }

    // Scan page: over the (shown) bar the camera image no longer sees the mouse – otherwise the overlay would show
    // its hover buttons (gear top right) when moving over the bar background
    MouseArea {
        z: 9
        visible: win.scanPage && win.navPos > 0.05
        x: 0; y: win.nav.y; width: win.width; height: win.nav.height + 14
        hoverEnabled: true
        acceptedButtons: Qt.NoButton
    }
    NavStatic {
        id: navFixed
        enabled: !win.covered
        width: parent.width
        height: 56
        y: -height * (1 - win.navPos)
        visible: win.navPos > 0.01
        z: 10
        items: shell.navItems
        current: win.page === "stats" ? "sessions" : win.page   // stats = a view of the Sessions tab
        backKey: shell.backKey === "stats" ? "sessions" : shell.backKey
        badges: shell.badges
        onPicked: function (key) { shell.pick(key, navFixed.clickDir) }
        leftPad: gamePick.leftW + 12   // game button
        rightPad: gamePick.rightW      // download circle while something is loading
        closeBtn: win.visibility === Window.FullScreen
        onCloseClicked: win.close()
        friendsOpen: friendsMenu.open
        friendsBadge: profilePage.requests.length > 0 && profilePage.requests.some(function (r) { return r.dir === "in" })
        onFriendsClicked: function (rx, by) { friendsMenu.open ? (friendsMenu.open = false) : friendsMenu.show(rx, by) }
    }
    FriendsMenu {   // Friends: menu on the profile button (no page of its own)
        id: friendsMenu
        enabled: !win.covered
        z: 13
        anchors.fill: parent
    }
    GamePicker {   // game button on the left of the bar + expanding row with the games
        id: gamePick
        enabled: !win.covered
        z: 12
        anchors.fill: parent
        navY: win.nav.y
        navH: win.nav.height
        // right edge of the circle: in front of the bar's icons
        ringRight: win.width - 16 - (navFixed.rightW - navFixed.rightPad) - 8
        shown: win.nav.visible
        onShownChanged: if (!shown) { open = false; listOpen = false }
    }
    // ---------- Preload: at startup load all pages in the background – afterwards switching is instant ----------
    // (previously every page was built on its first visit: long wait, sometimes even a crash)
    property int loadedCount: 0
    // Loading screen only until the visible page is ready – preloading builds the rest in the background
    // (previously it waited for all ten pages: several seconds more, with no benefit)
    property bool startReady: false
    property bool pageBuilding: false   // the shown page is still being built (Loading in its place)
    readonly property int pageCount: shell.pageKeys.length
    // Order per user (pageuse.py): after the start page the most used pages, rarely used ones right after, leisurely
    // – if you click one of them before that, it is built immediately
    Timer {
        id: preload
        interval: 60; repeat: true
        running: win.visible
        property int i: 0
        property var keys: shell.preloadEarly
        onTriggered: {
            var ks = keys
            while (i < ks.length && win.visited[ks[i]] === true) i++
            if (i >= ks.length) {
                stop()
                if (keys === shell.preloadEarly && shell.preloadLate.length) lateLoad.start()
                return
            }
            var v = Object.assign({}, win.visited); v[ks[i]] = true; win.visited = v
            i++
        }
    }
    // rarely used: right after, but leisurely (one every half second) – so the important ones are done first
    Timer { id: lateLoad; interval: 1500
            onTriggered: { preload.i = 0; preload.keys = shell.preloadLate; preload.interval = 500; preload.start() } }
    Timer { id: bootLimit; interval: 20000; running: win.visible }   // by then at the latest the start screen is gone
    Item {   // ui/busy.py: Python works on the GUI thread for a moment – the loading sign with what it does
        anchors.fill: parent
        z: 205
        visible: shell.busyText !== ""
        MouseArea { anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.AllButtons }   // nothing meanwhile
        Rectangle {
            anchors.centerIn: parent
            width: Math.max(220, busyDeck.implicitWidth + 48); height: busyDeck.implicitHeight + 36
            radius: 16; color: T.surface; border.width: 1; border.color: T.line2
            Loading { id: busyDeck; anchors.centerIn: parent; small: true; text: shell.busyText.trim() }
        }
    }
    BootShuffle {   // game switch: shuffle the deck with the game's name, then reveal softly
        anchors.fill: parent
        z: 199
        finished: !shell.gameSwitching
        title: shell.gameSwitchName
        sub: shell.text("opening …")
        big: true
    }
    // Start screen: little trading-card sayings (changing while it is shown) instead of „n / total“
    readonly property var bootWords: ["Booster werden geöffnet …", "Karten werden gesleevt …", "Decks werden gemischt …", "Starthand wird gezogen …", "Bulk wird sortiert …", "Binder werden aufgeschlagen …", "Toploader werden bereitgelegt …", "Playmat wird ausgerollt …", "Würfel werden gerollt …", "Hits werden gesucht …", "Pulls werden gezählt …", "Tauschordner wird aufgeschlagen …"]
    property int bootWord: Math.floor(Math.random() * bootWords.length)
    Timer { interval: 900; repeat: true; running: !win.startReady
             onTriggered: win.bootWord = (win.bootWord + 1 + Math.floor(Math.random() * 3)) % win.bootWords.length }
    BootShuffle {
        anchors.fill: parent
        z: 200
        done: win.loadedCount; total: win.pageCount
        sub: shell.text(win.bootWords[win.bootWord])
        finished: win.startReady || win.loadedCount >= win.pageCount || !bootLimit.running
    }

    // ---------- Minimized: tear down pages (app.trim_memory after 90 s), rebuild briefly when restored ----------
    // The data lives in Python (collection, decks, session …) – only the Qt Quick pages with their images are torn
    // down. The scan page stays (camera, running session). On restore: loading screen until the shown page is ready,
    // the others follow in the background as at startup.
    property bool pagesTrimmed: false
    property bool reviving: false
    function trimPages() {
        var v = {}
        if (win.visited["scan"] === true) v["scan"] = true
        preload.stop(); lateLoad.stop()
        win.visited = v
        win.pagesTrimmed = true
    }
    function revive() {
        win.pagesTrimmed = false
        if (win.visited[win.page] === true) { win.revived(); return }   // Scan page: was never gone
        win.reviving = true
        var v = Object.assign({}, win.visited); v[win.page] = true; win.visited = v
    }
    function revived() {
        win.reviving = false
        preload.i = 0; preload.keys = shell.preloadEarly; preload.interval = 60; preload.start()
    }
    onVisibilityChanged: if (win.pagesTrimmed && win.visibility !== Window.Minimized && win.visibility !== Window.Hidden) win.revive()
    BootShuffle {
        anchors.fill: parent
        z: 198
        finished: !win.reviving
        sub: shell.text(win.bootWords[win.bootWord])
    }
    Timer { interval: 900; repeat: true; running: win.reviving
             onTriggered: win.bootWord = (win.bootWord + 1 + Math.floor(Math.random() * 3)) % win.bootWords.length }

    // ---------- Page switch from Python ----------
    Connections {
        target: shell
        function onPageChanged(key, direction) {
            if (key === win.page) return
            var v = Object.assign({}, win.visited); v[key] = true; win.visited = v
            if (shell.lazyPages.indexOf(win.page) >= 0) { var l = Object.assign({}, win.leftAt); l[win.page] = Date.now(); win.leftAt = l }
            if (win.leftAt[key] !== undefined) { var l2 = Object.assign({}, win.leftAt); delete l2[key]; win.leftAt = l2 }
            win.prev = win.page
            navFixed.setCurrent(key, true)
            win.dir = direction !== 0 ? direction : win.nav.direction
            // list ⇄ stats are two views of one tab ("Sessions"): no page flip between them
            var oneTab = (key === "stats" && win.prev === "sessions") || (key === "sessions" && win.prev === "stats")
            win.page = key
            if (shell.animate && !oneTab) flip.restart(); else pages.u = 1
        }
        function onTipRequested(text, x, y) {
            tip.text = text
            tip.px = x; tip.py = y
        }
        function onToast(text) { toast.show(text) }
        function onTrimPages() { win.trimPages() }
        function onShowRequested(mode) {
            if (mode === "full") win.showFullScreen()
            else if (mode === "max") win.showMaximized()
            else if (mode === "normal") win.showNormal()
            else if (mode === "hide") { win.hide(); return }
            win.raise(); win.requestActivate()
        }
    }
    Component.onCompleted: navFixed.setCurrent(win.page, false)

    Shortcut { sequence: "F11"; onActivated: win.visibility === Window.FullScreen ? win.showMaximized() : win.showFullScreen() }
    Shortcut { sequences: [StandardKey.Back]; onActivated: shell.goBack() }

    // ---------- Dialogs as a page ----------
    SheetLayer {
        z: 50
        sheets: sheetHost
    }

    PopupLayer {
        z: 60
        pops: popupHost
    }

    // ---------- QML's own menus and choices (ContextMenu, DropList) as the light menu ----------
    property alias menuSheet: menuSheetItem
    MenuSheet {
        id: menuSheetItem
        objectName: "menuSheet"
        z: 70
    }

    // ---------- Tooltip ----------
    Rectangle {
        id: tip
        z: 100
        property string text: ""
        property real px: 0
        property real py: 0
        visible: opacity > 0
        opacity: text !== "" ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 140 } }
        width: Math.min(420, tipText.implicitWidth + 24)
        height: tipText.implicitHeight + 14
        x: Math.max(8, Math.min(win.width - width - 8, px - width / 2))
        y: py + height + 14 > win.height ? py - height - 44 : py + 8
        radius: 8
        color: T.surface2
        border.width: 1; border.color: T.line2
        Text {
            id: tipText
            anchors.centerIn: parent
            width: Math.min(396, implicitWidth)
            text: tip.text
            color: T.text2; font.family: T.font; font.pixelSize: 12
            wrapMode: Text.Wrap
        }
    }

    // ---------- Message bottom right ----------
    Rectangle {
        id: toast
        z: 100
        function show(t) { toastText.text = t; opacity = 1; toastT.restart() }
        opacity: 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 220 } }
        width: Math.min(620, toastText.implicitWidth + 32)
        height: toastText.implicitHeight + 20
        x: win.width - width - 24
        y: win.height - height - 24
        radius: 12
        color: T.surface2
        border.width: 1; border.color: T.line2
        Text {
            id: toastText
            anchors.centerIn: parent
            width: Math.min(588, implicitWidth)
            color: T.text; font.family: T.font; font.pixelSize: 13
            wrapMode: Text.Wrap
        }
        Timer { id: toastT; interval: 6000; onTriggered: toast.opacity = 0 }
    }
}

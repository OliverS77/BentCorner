// First start, part 1 – small Qt Quick window before the program: 1 Language (flags) · 2 Storage location (preset,
// [OK] or [Customise]; not in a portable copy) · 3 Which games? After that it continues in the program window
// (onboarding.py). Leaner setup 0.9.8 (lead 13.11.): one sentence per step, the rest behind „▸ More“. Folder choice
// with the file browser in the same window. Logic: setup (setupui.FirstRunBackend). Switching language rebuilds the
// content (all texts).
import QtQuick
import QtQuick.Window
import "components"

Window {
    id: win
    width: 760; height: 600 + (setup.found.length > 0 ? 70 + 68 * Math.min(setup.found.length, 3) : 0)
    property bool more: false   // „▸ More“ on the games page
    minimumWidth: 640; minimumHeight: 560
    visible: false
    color: T.bg
    title: shell.text("Welcome to Bent°Corner")

    Connections {
        target: setup
        function onLangChanged() { body.active = false; body.active = true; win.title = shell.text("Welcome to Bent°Corner") }
    }

    component Choice: Rectangle {
        id: ch
        property string key
        property string label
        property string sub
        property Item extra: null
        readonly property bool on: setup.choice === key
        width: parent.width; height: 56; radius: 12
        color: on ? T.surface2 : (chh.hovered ? T.surface : "transparent")
        border.width: 1; border.color: on ? T.line2 : T.line
        Rectangle {
            x: 16; anchors.verticalCenter: parent.verticalCenter
            width: 18; height: 18; radius: 9
            color: "transparent"; border.width: 2; border.color: ch.on ? T.hi : T.line2
            Rectangle { anchors.centerIn: parent; width: 8; height: 8; radius: 4; color: T.hi; visible: ch.on }
        }
        Column {
            x: 48; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 60 - (ch.extra ? ch.extra.width + 12 : 0)
            Text { text: ch.label; color: T.text; font.family: T.font; font.pixelSize: 15; font.bold: ch.on }
            Text { text: ch.sub; visible: ch.sub !== ""; width: parent.width; elide: Text.ElideMiddle
                   color: T.dim; font.family: T.font; font.pixelSize: 12 }
        }
        HoverHandler { id: chh; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: setup.setChoice(ch.key) }
    }

    // A collection already on this PC: chosen by brightness only (dim → nearly normal on hover → normal when chosen),
    // nothing preselected (lead 06.11.2026). Not reachable: [Check again] instead.
    component Found: Rectangle {
        id: fd
        property var entry
        readonly property bool on: setup.choice === entry.key
        width: parent.width; height: 56; radius: 12
        color: on ? T.surface2 : "transparent"
        border.width: 1; border.color: on ? T.line2 : T.line
        opacity: on ? 1.0 : (fdh.hovered ? 0.85 : 0.6)
        Column {
            x: 16; anchors.verticalCenter: parent.verticalCenter
            width: parent.width - 32 - (recheckBtn.visible ? recheckBtn.width + 12 : 0)
            Text { text: fd.entry.path; width: parent.width; elide: Text.ElideMiddle
                   color: T.text; font.family: T.font; font.pixelSize: 15; font.bold: fd.on }
            Text { text: fd.entry.sub; width: parent.width; elide: Text.ElideRight
                   color: T.dim; font.family: T.font; font.pixelSize: 12 }
        }
        Btn { id: recheckBtn; visible: !fd.entry.reachable; anchors.right: parent.right; anchors.rightMargin: 12
              anchors.verticalCenter: parent.verticalCenter; height: 34; compact: true
              text: shell.text("Check again"); onClicked: setup.recheck() }
        HoverHandler { id: fdh; cursorShape: fd.entry.reachable ? Qt.PointingHandCursor : Qt.ArrowCursor }
        TapHandler { enabled: fd.entry.reachable; onTapped: setup.setChoice(fd.entry.key) }
    }

    // Flag (drawn): "en" = Union Jack, "de" = black-red-gold
    component Flag: Canvas {
        property string code
        width: 120; height: 72
        onAvailableChanged: if (available) requestPaint()
        Component.onCompleted: Qt.callLater(requestPaint)
        onPaint: {
            var g = getContext("2d"), w = width, h = height
            g.reset()
            if (code === "de") {
                g.fillStyle = "#000000"; g.fillRect(0, 0, w, h / 3)
                g.fillStyle = "#dd0000"; g.fillRect(0, h / 3, w, h / 3)
                g.fillStyle = "#ffce00"; g.fillRect(0, 2 * h / 3, w, h / 3 + 1)
                return
            }
            g.fillStyle = "#012169"; g.fillRect(0, 0, w, h)
            g.lineCap = "butt"
            g.strokeStyle = "#ffffff"; g.lineWidth = h * 0.2
            g.beginPath(); g.moveTo(0, 0); g.lineTo(w, h); g.moveTo(w, 0); g.lineTo(0, h); g.stroke()
            g.strokeStyle = "#c8102e"; g.lineWidth = h * 0.066
            g.beginPath(); g.moveTo(0, 0); g.lineTo(w, h); g.moveTo(w, 0); g.lineTo(0, h); g.stroke()
            g.fillStyle = "#ffffff"; g.fillRect(w / 2 - h * 0.167, 0, h * 0.333, h); g.fillRect(0, h / 2 - h * 0.167, w, h * 0.333)
            g.fillStyle = "#c8102e"; g.fillRect(w / 2 - h * 0.1, 0, h * 0.2, h); g.fillRect(0, h / 2 - h * 0.1, w, h * 0.2)
        }
    }

    Loader {
        id: body
        anchors.fill: parent
        visible: setup.browser === null
        sourceComponent: Item {
            // ---------- Header: „Step n of m“ – the same line as in the program window (whole setup counted) ----------
            Text {
                x: 32; y: 26
                text: shell.text("Step " + setup.stepNo + " of " + setup.steps)   // locales RULES: „Schritt n von m“
                color: T.dim; font.family: T.font; font.pixelSize: 13
            }

            // ---------- 1: Language ----------
            Column {
                visible: setup.page === 0
                x: 32; y: 60; width: parent.width - 64
                spacing: 14
                Lockup { size: 32; color: T.text }   // the brand: long version (card + BENT°CORNER)
                Text { width: parent.width; wrapMode: Text.Wrap; text: shell.text("Choose your language.")
                       color: T.text2; font.family: T.font; font.pixelSize: 15 }
                Item { width: 1; height: 10 }
                Row {
                    spacing: 18
                    Repeater {
                        model: [{"code": "en", "name": "English"}, {"code": "de", "name": "Deutsch"}]
                        Rectangle {
                            id: ft
                            required property var modelData
                            readonly property bool on: setup.lang === modelData.code
                            width: 168; height: 150; radius: 14
                            color: on ? T.surface2 : (fh.hovered ? T.surface : "transparent")
                            border.width: on ? 2 : 1; border.color: on ? T.hi : T.line
                            opacity: on || fh.hovered ? 1 : 0.55
                            Column {
                                anchors.centerIn: parent; spacing: 12
                                Rectangle { width: 122; height: 74; radius: 6; color: "transparent"; clip: true
                                            border.width: 1; border.color: T.line2
                                            Flag { x: 1; y: 1; width: 120; height: 72; code: ft.modelData.code } }
                                Text { anchors.horizontalCenter: parent.horizontalCenter; text: ft.modelData.name
                                       color: T.text; font.family: T.font; font.pixelSize: 15; font.bold: ft.on }
                            }
                            HoverHandler { id: fh; cursorShape: Qt.PointingHandCursor }
                            TapHandler { onTapped: setup.setLang(ft.modelData.code) }
                        }
                    }
                }
            }

            // ---------- 2: Storage location ----------
            Column {
                id: main
                visible: setup.page === 1
                x: 32; y: 60; width: parent.width - 64
                spacing: 12
                Text { width: parent.width; wrapMode: Text.Wrap
                       text: shell.text("Your collection is stored here:")
                       color: T.text; font.family: T.display; font.pixelSize: 28 }
                // preset (lead 13.11.): the folder, [Customise] opens today's choices
                Rectangle {
                    visible: !setup.customise
                    width: parent.width; height: 56; radius: 12
                    color: T.surface2; border.width: 1; border.color: T.line2
                    Text { x: 16; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 32
                           text: setup.choice === "port" ? setup.portPath : setup.docsPath; elide: Text.ElideMiddle
                           color: T.text; font.family: T.font; font.pixelSize: 15 }
                }
                Btn { visible: !setup.customise; height: 36; compact: true; text: shell.text("Customise")
                      onClicked: setup.setCustomise(true) }
                // collections already on this PC (only shown – nothing is copied or moved)
                Text { visible: setup.customise && setup.found.length > 0; width: parent.width; wrapMode: Text.Wrap
                       text: setup.found.length === 1 ? shell.text("Found a collection on this PC – use it?")
                                                     : shell.text("Found collections on this PC – which one is yours?")
                       color: T.text; font.family: T.font; font.pixelSize: 15; font.bold: true }
                Repeater { model: setup.customise ? setup.found : []; Found { required property var modelData; entry: modelData } }
                Text { visible: setup.customise; text: shell.text("I already have a collection – choose its folder")
                       color: T.text2; font.family: T.font; font.pixelSize: 13; font.underline: hav.hovered
                       HoverHandler { id: hav; cursorShape: Qt.PointingHandCursor }
                       TapHandler { onTapped: setup.browse() } }
                Text { visible: setup.customise && setup.found.length > 0; text: shell.text("Or start a new, empty collection:")
                       color: T.dim; font.family: T.font; font.pixelSize: 13; topPadding: 6 }
                Choice { key: "docs"; visible: setup.customise; label: shell.text("Recommended"); sub: setup.docsPath }
                Choice { key: "port"; visible: setup.customise && setup.portableOk; label: shell.text("Next to the program (portable, e.g. for a USB stick)"); sub: setup.portPath }
                Choice {
                    id: other
                    visible: setup.customise
                    key: "other"; label: shell.text("Other folder …")
                    sub: setup.other !== "" ? setup.other : shell.text("Choose folder …")
                    extra: browseBtn
                    Btn { id: browseBtn; visible: other.on; anchors.right: parent.right; anchors.rightMargin: 12
                          anchors.verticalCenter: parent.verticalCenter; height: 34; compact: true
                          text: shell.text("Browse …"); onClicked: setup.browse() }
                }
                Text { visible: setup.error !== ""; width: parent.width; wrapMode: Text.Wrap; text: setup.error
                       color: "#e08080"; font.family: T.font; font.pixelSize: 13 }
            }

            // ---------- 3: Games ----------
            Column {
                id: gcol
                visible: setup.page === 2
                x: 32; y: 60; width: parent.width - 64
                spacing: 12
                Text { text: shell.text("Which games do you want to scan?"); color: T.text; font.family: T.display; font.pixelSize: 28 }
                Text { text: (win.more ? "▾ " : "▸ ") + shell.text("More"); color: T.dim; font.family: T.font
                       font.pixelSize: 13; font.underline: mh.hovered
                       HoverHandler { id: mh; cursorShape: Qt.PointingHandCursor }
                       TapHandler { onTapped: win.more = !win.more } }
                Text { visible: win.more; width: parent.width; wrapMode: Text.Wrap
                       text: shell.text("Tap a card back – you can pick more than one. Bent°Corner gets everything it needs to recognize cards right away, including cards in other languages.")
                       color: T.text2; font.family: T.font; font.pixelSize: 14 }
                Item { width: 1; height: 6 }
                Row {
                    spacing: 16
                    Repeater {
                        model: setup.gameTiles
                        Item {
                            id: gt
                            required property var modelData
                            readonly property bool on: setup.games.indexOf(modelData.key) >= 0
                            // as many games as there are, side by side (at most 210 wide)
                            width: Math.min(210, (gcol.width - 16 * (setup.gameTiles.length - 1)) / setup.gameTiles.length)
                            height: 300
                            opacity: on ? 1 : (modelData.ready && gh.hovered ? 0.8 : 0.4)
                            Behavior on opacity { NumberAnimation { duration: 140 } }
                            Rectangle {
                                anchors.horizontalCenter: parent.horizontalCenter
                                width: 148; height: 210; radius: 14; color: "transparent"
                                border.width: gt.on ? 2 : 0; border.color: T.hi
                                PixelBack { anchors.centerIn: parent; visible: gt.modelData.back !== ""; back: gt.modelData.back; h: 200 }
                                Rectangle {   // „More“: three empty card backs one behind the other
                                    visible: gt.modelData.back === ""
                                    anchors.centerIn: parent; width: 140; height: 200; radius: 12
                                    color: T.surface; border.width: 1; border.color: T.line2
                                    Text { anchors.centerIn: parent; text: "+"; color: T.dim; font.family: T.display; font.pixelSize: 64 }
                                }
                            }
                            Column {
                                y: 218; width: parent.width; spacing: 4
                                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: gt.modelData.name
                                       color: T.text; font.family: T.font; font.pixelSize: 15; font.bold: gt.on }
                                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                                       text: gt.modelData.info; color: T.dim; font.family: T.font; font.pixelSize: 12 }
                            }
                            HoverHandler { id: gh; enabled: gt.modelData.ready; cursorShape: Qt.PointingHandCursor }
                            TapHandler { enabled: gt.modelData.ready; onTapped: setup.toggleGame(gt.modelData.key) }
                        }
                    }
                }
                Text { visible: setup.error !== ""; width: parent.width; wrapMode: Text.Wrap; text: setup.error
                       color: "#e08080"; font.family: T.font; font.pixelSize: 13 }
            }

            // ---------- bottom: Back / Next ----------
            Btn {
                visible: setup.canBack
                anchors.left: parent.left; anchors.bottom: parent.bottom; anchors.margins: 28
                height: 42; width: 130; text: shell.text("Back")
                onClicked: setup.back()
            }
            Text {
                visible: setup.page === 2 && setup.games.length === 0
                anchors.right: nextBtn.left; anchors.rightMargin: 14; anchors.verticalCenter: nextBtn.verticalCenter
                text: shell.text("Pick at least one game."); color: T.dim; font.family: T.font; font.pixelSize: 13
            }
            Btn {
                id: nextBtn
                anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 28
                height: 42; width: 170; primary: true
                enabled: setup.canGoOn && (setup.page !== 2 || setup.games.length > 0)
                text: setup.page === 2 ? shell.text("Let's go") : (setup.page === 1 && !setup.customise ? shell.text("OK")
                                                                                                     : shell.text("Next"))
                onClicked: setup.next()
            }
        }
    }

    // Folder choice in the same window
    Item {
        anchors.fill: parent; anchors.margins: 24
        visible: setup.browser !== null
        Text { id: bt; text: (setup.lang, shell.text("Choose a folder for your data")); color: T.text; font.family: T.font; font.pixelSize: 20; font.bold: true }
        Loader {
            y: bt.height + 14; width: parent.width; height: parent.height - y
            active: setup.browser !== null
            sourceComponent: FileBrowser { fb: setup.browser }
        }
    }
    Component.onCompleted: { x = (Screen.width - width) / 2; y = (Screen.height - height) / 2 }
}

// Stats: tabs Sessions · Trade · Collection, filters (pack types, tags) and the tab's content with the
// charts. Logic: statsPage (qstats.py) via statsview.StatsPage.
import QtQuick
import "../components"

Item {
    id: page
    property string key
    readonly property var sp: statsPage
    onVisibleChanged: sp.setActive(visible)
    Component.onCompleted: sp.setActive(visible)

    SessionsHead {   // the "Sessions" tab: List | Stats
        id: head
        x: 22; y: 12; width: page.width - 42
        view: "stats"
        sub: page.sp.hasPacks ? shell.text("How are your packs, trades and collection doing?")
                              : shell.text("How are your logs, trades and collection doing?")
    }
    Item {
        id: bar
        x: 20; y: head.y + head.height + 12
        width: page.width - 40; height: 38
        Row {
            spacing: 8
            Repeater {
                model: page.sp.tabs
                Btn { required property var modelData
                      height: 38; width: 140
                      text: modelData.text; checkable: true; checked: page.sp.tab === modelData.key
                      onClicked: page.sp.setTab(modelData.key) }
            }
        }
        Btn {
            anchors.right: parent.right
            visible: page.sp.filterShown
            height: 34; width: Math.max(160, implicitWidth); compact: true
            text: page.sp.filterText.replace("  ▾", "") + (page.sp.filterOpen ? "  ▴" : "  ▾")
            active: page.sp.filterOpen
            tip: page.sp.hasPacks ? shell.text("Which pack types and tags count towards the log stats")
                                  : shell.text("Which tags count towards the log stats")
            onClicked: page.sp.toggleFilter()
        }
    }
    Rectangle {
        id: filt
        x: 20; y: bar.y + bar.height + (shown ? 10 : 0)
        width: page.width - 40
        readonly property bool shown: page.sp.filterOpen && page.sp.filterShown
        height: shown && fm.item ? fm.item.height + 22 : 0
        visible: shown
        radius: 14
        color: Qt.darker(T.surface, 1.1); border.width: 1; border.color: T.line
        Loader {   // the filter only while it is open
            id: fm; x: 16; y: 11; width: parent.width - 32
            active: filt.shown
            sourceComponent: Mirror { width: fm.width; mirror: page.sp.filter }
        }
    }
    Flickable {
        id: fl
        ScrollHint {}
        x: 20; y: filt.y + filt.height + 12
        width: page.width - 40; height: page.height - y - 10
        contentHeight: body.height + 20
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickDeceleration: 3500
        // one body per tab: made on its first visit, then kept hidden (switching back costs nothing)
        Item {
            id: body
            width: fl.width - 14
            height: shownBody ? shownBody.height : 0
            property Item shownBody: null
            Repeater {
                model: page.sp.tabs   // fixed – a tab's body is never made anew by the list
                Loader {
                    id: tl
                    required property var modelData
                    readonly property bool on: page.sp.tab === modelData.key
                    active: on || page.sp.seenTabs.indexOf(modelData.key) >= 0
                    // hidden by opacity, not visible: false – the scene keeps what it drew for the tab (a tab made
                    // visible again was drawn anew, ~0.3 s), at opacity 0 nothing of it is painted; no clicks there
                    opacity: on ? 1 : 0
                    enabled: on
                    width: body.width
                    onOnChanged: if (on && item) body.shownBody = item
                    onLoaded: if (on) body.shownBody = item
                    sourceComponent: Mirror { width: body.width; mirror: page.sp.bodyOf(tl.modelData.key) }
                }
            }
        }
    }
    Connections { target: page.sp; function onChanged() { } }
}

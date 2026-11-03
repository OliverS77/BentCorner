// Date + time: shows „Mo., 05.10.2026 · 18:00“; a click expands calendar and time below it (in the window).
// value: "yyyy-MM-ddTHH:mm"; every change reports changed(new value).
import QtQuick

Column {
    id: root
    property string value: ""
    property string loc: "de_DE"
    property bool open: false
    signal changed(string value)
    spacing: 6

    readonly property var locale: Qt.locale(loc)
    readonly property date dt: value ? new Date(value.substring(0, 4), parseInt(value.substring(5, 7)) - 1, value.substring(8, 10),
                                                 value.substring(11, 13) || 0, value.substring(14, 16) || 0) : new Date()
    property int vy: dt.getFullYear()
    property int vm: dt.getMonth()
    onOpenChanged: if (open) { vy = dt.getFullYear(); vm = dt.getMonth() }

    function pad(n) { return (n < 10 ? "0" : "") + n }
    function emit(y, m, d, hh, mm) {
        var last = new Date(y, m + 1, 0).getDate()
        d = Math.min(d, last)
        changed(y + "-" + pad(m + 1) + "-" + pad(d) + "T" + pad(hh) + ":" + pad(mm))
    }

    Btn {
        width: Math.min(root.width, Math.max(260, implicitWidth)); height: 34; compact: true
        checkable: true; checked: root.open
        text: root.dt.toLocaleString(root.locale, "ddd, dd.MM.yyyy  ·  HH:mm") + "    ✎"
        tip: shell.text("Click to change date and time")
        onClicked: root.open = !root.open
    }
    Rectangle {
        visible: root.open
        width: Math.min(root.width, 470); height: panel.implicitHeight + 20
        radius: 12; color: Qt.darker(T.surface, 1.1); border.width: 1; border.color: T.line
        Row {
            id: panel
            x: 10; y: 10; spacing: 14
            Column {
                spacing: 4
                Item {
                    width: 7 * 38; height: 30
                    Btn { width: 30; height: 28; compact: true; text: "‹"
                          onClicked: { if (root.vm === 0) { root.vm = 11; root.vy-- } else root.vm-- } }
                    Text { anchors.centerIn: parent; text: root.locale.standaloneMonthName(root.vm) + " " + root.vy
                           color: T.text; font.family: T.font; font.pixelSize: 14; font.bold: true }
                    Btn { anchors.right: parent.right; width: 30; height: 28; compact: true; text: "›"
                          onClicked: { if (root.vm === 11) { root.vm = 0; root.vy++ } else root.vm++ } }
                }
                Row {
                    Repeater {
                        model: 7
                        Text { required property int index; width: 38; horizontalAlignment: Text.AlignHCenter
                               text: root.locale.dayName((index + 1) % 7, Locale.ShortFormat)
                               color: T.dim; font.family: T.font; font.pixelSize: 11 }
                    }
                }
                Grid {
                    columns: 7
                    readonly property int first: (new Date(root.vy, root.vm, 1).getDay() + 6) % 7   // Monday first
                    readonly property int days: new Date(root.vy, root.vm + 1, 0).getDate()
                    Repeater {
                        model: 42
                        Rectangle {
                            required property int index
                            readonly property int day: index - parent.first + 1
                            readonly property bool real: day >= 1 && day <= parent.days
                            readonly property bool sel: real && day === root.dt.getDate() && root.vm === root.dt.getMonth()
                                                        && root.vy === root.dt.getFullYear()
                            width: 38; height: 30; radius: 8
                            visible: index < 35 || parent.first + parent.days > 35
                            color: sel ? T.surface2 : (dh.hovered && real ? Qt.lighter(T.surface, 1.2) : "transparent")
                            border.width: sel ? 1 : 0; border.color: T.line2
                            Text { anchors.centerIn: parent; text: parent.real ? parent.day : ""
                                   color: parent.sel ? T.text : T.text2; font.family: T.font; font.pixelSize: 13 }
                            HoverHandler { id: dh; cursorShape: parent.real ? Qt.PointingHandCursor : Qt.ArrowCursor }
                            TapHandler { enabled: parent.real
                                         onTapped: root.emit(root.vy, root.vm, parent.day, root.dt.getHours(), root.dt.getMinutes()) }
                        }
                    }
                }
            }
            Column {
                spacing: 6
                Text { text: shell.text("Time"); color: T.muted; font.family: T.font; font.pixelSize: 13; font.bold: true }
                Row {
                    spacing: 4
                    SpinField { width: 74; from: 0; to: 23; value: root.dt.getHours()
                                onCommitted: function (v) { root.emit(root.dt.getFullYear(), root.dt.getMonth(), root.dt.getDate(), v, root.dt.getMinutes()) } }
                    Text { text: ":"; color: T.text; font.pixelSize: 16; anchors.verticalCenter: parent.verticalCenter }
                    SpinField { width: 74; from: 0; to: 59; value: root.dt.getMinutes()
                                onCommitted: function (v) { root.emit(root.dt.getFullYear(), root.dt.getMonth(), root.dt.getDate(), root.dt.getHours(), v) } }
                }
                Item { width: 1; height: 120 }
                Btn { width: 100; height: 32; compact: true; text: shell.text("Done"); onClicked: root.open = false }
            }
        }
    }
}

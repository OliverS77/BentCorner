// Simple table: header row, rows (texts), one selected row. Click selects, double click opens.
// No frame of its own: a header line with a divider below (design rule: no boxes in boxes).
// cols: [{title, stretch}] – stretch columns share the space, the others take their text width.
import QtQuick

Rectangle {
    id: root
    property var cols: []
    property var rows: []             // [[text, …], …]
    property int sel: -1
    property string empty: ""
    property real rowH: 30
    signal clicked(int row)
    signal doubleClicked(int row)
    color: "transparent"

    // column widths: fixed columns by their widest text (measured), the rest for stretch
    FontMetrics { id: fm; font.family: T.font; font.pixelSize: 13 }
    readonly property var widths: {
        var n = cols.length, w = [], fixed = 0, flex = 0
        for (var c = 0; c < n; c++) {
            if (cols[c].stretch) { w.push(-1); flex++; continue }
            var m = fm.advanceWidth(cols[c].title || "")
            for (var r = 0; r < rows.length; r++) m = Math.max(m, fm.advanceWidth(rows[r][c] || ""))
            w.push(m + 24); fixed += m + 24
        }
        var rest = Math.max(40, (width - fixed) / Math.max(1, flex))
        for (c = 0; c < n; c++) if (w[c] < 0) w[c] = rest
        return w
    }

    Row {
        id: head
        x: 0; y: 0; height: 26
        Repeater {
            model: root.cols
            Text {
                required property var modelData
                required property int index
                width: root.widths[index] || 0; height: 26; leftPadding: 8; verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight; text: modelData.title || ""
                color: T.muted; font.family: T.font; font.pixelSize: 12; font.bold: true
            }
        }
    }
    Rectangle { y: head.y + head.height; width: root.width; height: 1; color: T.line }
    ListView {
        ScrollHint {}
        id: lv
        y: head.y + head.height + 3; width: root.width; height: root.height - y
        clip: true; boundsBehavior: Flickable.StopAtBounds
        model: root.rows
        onCountChanged: positionViewAtEnd()
        delegate: Rectangle {
            id: rw
            required property var modelData
            required property int index
            width: lv.width; height: root.rowH; radius: 7
            color: index === root.sel ? T.surface2 : (rh.hovered ? Qt.lighter(T.surface, 1.15) : "transparent")
            Row {
                Repeater {
                    model: rw.modelData
                    Text {
                        required property var modelData
                        required property int index
                        width: root.widths[index] || 0; height: root.rowH; leftPadding: 8; verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight; text: modelData; color: T.text; font.family: T.font; font.pixelSize: 13
                    }
                }
            }
            HoverHandler { id: rh; cursorShape: Qt.PointingHandCursor }
            TapHandler {
                onTapped: root.clicked(rw.index)
                onDoubleTapped: root.doubleClicked(rw.index)
            }
        }
    }
    Text {
        visible: root.rows.length === 0 && root.empty !== ""
        anchors.centerIn: lv; width: lv.width - 30; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
        text: root.empty; color: T.dim; font.family: T.font; font.pixelSize: 13
    }
}

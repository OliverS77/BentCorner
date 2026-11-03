// Pin bar: all prints of a card, from 5 prints on with a search field (set code, set name, number).
import QtQuick

Column {
    id: pp
    property var prints: []
    property int searchFrom: 5   // from this many prints on there is the search field
    property color fadeColor: T.bg   // colour behind the bar (soft edge)
    signal picked(string id)
    spacing: 6
    property string q: ""
    onPrintsChanged: if (!prints.length) q = ""
    readonly property var shown: {
        var t = q.trim().toLowerCase()
        if (t === "") return prints
        var out = []
        for (var i = 0; i < prints.length; i++) {
            var p = prints[i]
            var hay = (p.set + " " + (p.sname || "") + " " + p.number + " " + p.set + p.number).toLowerCase()
            var ok = true, parts = t.split(/\s+/)
            for (var j = 0; j < parts.length; j++) if (hay.indexOf(parts[j]) < 0) { ok = false; break }
            if (ok) out.push(p)
        }
        return out
    }
    SearchField {
        visible: pp.prints.length >= pp.searchFrom
        width: Math.min(pp.width, 360); height: 32
        placeholder: shell.text("Search print: set, code, number …")
        text: pp.q
        onEdited: function (t) { pp.q = t }
    }
    Text {
        visible: pp.q !== "" && pp.shown.length === 0
        text: shell.text("No print matches.")
        color: T.muted; font.family: T.font; font.pixelSize: 13
    }
    PrintStrip {
        width: pp.width
        visible: pp.shown.length > 0
        prints: pp.shown
        fadeColor: pp.fadeColor
        onPicked: function (id) { pp.picked(id) }
    }
}

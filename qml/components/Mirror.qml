// Mirrored form (qform.Form) as a Qt Quick column.
import QtQuick

Column {
    id: m
    property var mirror
    spacing: 6
    // key -> MirrorNode: a value change (form.valsChanged) re-reads just that node, through one Connections for the
    // whole form instead of one per node
    QtObject { id: hub; property var nodes: ({}) }
    Connections {
        target: m.mirror
        ignoreUnknownSignals: true
        function onValsChanged(keys) { for (var k in keys) { var nd = hub.nodes[k]; if (nd) nd.nv = nd.read() } }
    }
    Repeater {
        model: m.mirror ? m.mirror.tree : []
        delegate: MirrorNode { required property var modelData; node: modelData; mirror: m.mirror; hub: hub; width: m.width }
    }
}

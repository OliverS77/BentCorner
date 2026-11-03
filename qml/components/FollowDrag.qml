// Drag handler for items that move into another parent while dragged (ParentChange onto the page/window, so they
// float above everything): a plain DragHandler keeps calculating in the old parent's coordinates – the item then
// jumps by that parent's offset and hangs beside the mouse. Here the item follows the mouse itself: the point where
// it was grabbed stays exactly under the cursor, whatever parent it is in.
import QtQuick

DragHandler {
    id: h
    target: null
    property Item item: parent
    property real gx: 0
    property real gy: 0
    property point dropAt: Qt.point(0, 0)   // where the item was let go (window coordinates of its corner)
    onActiveChanged: if (active) { gx = centroid.pressPosition.x; gy = centroid.pressPosition.y; follow() }
    onCentroidChanged: if (active) follow()
    function follow() {
        if (!item || !item.parent) return
        dropAt = Qt.point(centroid.scenePosition.x - gx, centroid.scenePosition.y - gy)
        var p = item.parent.mapFromItem(null, dropAt.x, dropAt.y)
        item.x = p.x
        item.y = p.y
    }
    // Back into the grid after letting go (GridView cells): a GridView sets x/y of a delegate only when it lays it out
    // anew – after the drag the tile stayed where it was dropped until the next rebuild (Oliver, 0.9.2.87). A Row/Flow
    // (binders, friends) re-lays out its children by itself. settle(x, y) glides from the drop point to the cell
    // (once the ParentChange is undone); a reorder or merge rebuilds the model and puts the tile in its new place.
    function settle(tx, ty) {
        Qt.callLater(function () {
            if (!item || !item.parent || active) return
            if (!shell.animate) { item.x = tx; item.y = ty; return }
            var p = item.parent.mapFromItem(null, dropAt.x, dropAt.y)
            item.x = p.x; item.y = p.y
            sx.to = tx; sy.to = ty
            home.restart()
        })
    }
    function settleIn(view, index) {   // the cell of a GridView (flow left to right)
        var cols = Math.max(1, Math.floor(view.width / view.cellWidth))
        settle(index % cols * view.cellWidth, Math.floor(index / cols) * view.cellHeight)
    }
    property ParallelAnimation home: ParallelAnimation {
        NumberAnimation { id: sx; target: h.item; property: "x"; duration: 220 * shell.speed; easing.type: Easing.OutCubic }
        NumberAnimation { id: sy; target: h.item; property: "y"; duration: 220 * shell.speed; easing.type: Easing.OutCubic }
    }
}

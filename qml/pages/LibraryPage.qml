// Library: the library view (components/LibraryView.qml) with the collection. Logic: libraryPage (qlibrary.py).
import QtQuick
import "../components"

Item {
    id: page
    property string key
    LibraryView {
        anchors.fill: parent
        lib: libraryPage
    }
}
